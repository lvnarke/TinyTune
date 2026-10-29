"""Stepped, constant-arrival-rate load test with a machine-readable report."""

import asyncio
import json
import math
import os
import random
import secrets
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx


TARGET_URL = os.getenv("TARGET_URL", "http://localhost:8080").rstrip("/")
RUN_LABEL = os.getenv("RUN_LABEL", "optimized")
STEP_RATES = [int(value) for value in os.getenv("STEP_RATES", "10,25,50,100,200,400").split(",")]
STEP_DURATION = float(os.getenv("STEP_DURATION_SECONDS", "10"))
P95_LIMIT_MS = float(os.getenv("P95_LIMIT_MS", "250"))
ERROR_LIMIT_PERCENT = float(os.getenv("ERROR_LIMIT_PERCENT", "1"))
RESULTS_DIR = Path(os.getenv("RESULTS_DIR", "results"))


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1))
    return ordered[index]


async def wait_until_ready(client: httpx.AsyncClient) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            response = await client.get(f"{TARGET_URL}/health/ready")
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        await asyncio.sleep(1)
    raise RuntimeError(f"TinyTune was not ready at {TARGET_URL} after 60 seconds")


async def create_fixture(client: httpx.AsyncClient) -> tuple[str, str]:
    client.headers["X-TinyTune-Request"] = "1"
    signup = await client.post(f"{TARGET_URL}/auth/signup", json={"username":"bench_"+secrets.token_hex(6), "name":"Python load fixture", "password":secrets.token_urlsafe(24)})
    signup.raise_for_status()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    playlist_response = await client.post(
        f"{TARGET_URL}/api/v1/playlists", json={"name": f"load-test-{RUN_LABEL}-{stamp}"}
    )
    playlist_response.raise_for_status()
    playlist_id = playlist_response.json()["id"]
    track_response = await client.post(
        f"{TARGET_URL}/api/v1/playlists/{playlist_id}/tracks",
        json={"title": "Saturation Point", "artist": "The Backpressures"},
    )
    track_response.raise_for_status()
    return playlist_id, track_response.json()["id"]


async def make_request(
    client: httpx.AsyncClient,
    playlist_id: str,
    track_id: str,
    sequence: int,
    scheduled_at: float,
) -> dict:
    now = time.perf_counter()
    if scheduled_at > now:
        await asyncio.sleep(scheduled_at - now)
    started = time.perf_counter()
    try:
        if sequence % 10 < 7:
            response = await client.get(f"{TARGET_URL}/api/v1/playlists/{playlist_id}")
        else:
            response = await client.post(
                f"{TARGET_URL}/api/v1/playlists/{playlist_id}/plays",
                headers={"Idempotency-Key": f"{RUN_LABEL}-{sequence}-{started}"},
                json={"track_id": track_id},
            )
        elapsed_ms = (time.perf_counter() - started) * 1000
        return {
            "latency_ms": elapsed_ms,
            "ok": 200 <= response.status_code < 300,
            "status": response.status_code,
            "error": None if response.status_code < 400 else response.text[:200],
        }
    except Exception as exc:
        return {
            "latency_ms": (time.perf_counter() - started) * 1000,
            "ok": False,
            "status": 0,
            "error": type(exc).__name__,
        }


async def run_step(
    client: httpx.AsyncClient, playlist_id: str, track_id: str, target_rps: int
) -> dict:
    total = max(1, int(target_rps * STEP_DURATION))
    step_started = time.perf_counter()
    tasks = [
        asyncio.create_task(
            make_request(
                client,
                playlist_id,
                track_id,
                sequence,
                step_started + (sequence / target_rps),
            )
        )
        for sequence in range(total)
    ]
    responses = await asyncio.gather(*tasks)
    elapsed = time.perf_counter() - step_started
    latencies = [item["latency_ms"] for item in responses]
    errors = [item for item in responses if not item["ok"]]
    error_percent = 100 * len(errors) / len(responses)
    achieved_rps = len(responses) / elapsed
    p95 = percentile(latencies, 0.95)
    saturated_reasons = []
    if p95 > P95_LIMIT_MS:
        saturated_reasons.append(f"p95 {p95:.1f} ms > {P95_LIMIT_MS:.0f} ms")
    if error_percent > ERROR_LIMIT_PERCENT:
        saturated_reasons.append(
            f"errors {error_percent:.2f}% > {ERROR_LIMIT_PERCENT:.2f}%"
        )
    if achieved_rps < target_rps * 0.90:
        saturated_reasons.append(
            f"achieved {achieved_rps:.1f} rps < 90% of target"
        )
    status_counts: dict[str, int] = {}
    for item in responses:
        key = str(item["status"])
        status_counts[key] = status_counts.get(key, 0) + 1
    return {
        "target_rps": target_rps,
        "requests": len(responses),
        "elapsed_seconds": round(elapsed, 3),
        "achieved_rps": round(achieved_rps, 2),
        "latency_ms": {
            "mean": round(statistics.fmean(latencies), 2),
            "p50": round(percentile(latencies, 0.50), 2),
            "p95": round(p95, 2),
            "p99": round(percentile(latencies, 0.99), 2),
            "max": round(max(latencies), 2),
        },
        "errors": len(errors),
        "error_percent": round(error_percent, 3),
        "status_counts": status_counts,
        "saturated": bool(saturated_reasons),
        "saturation_reasons": saturated_reasons,
    }


def markdown_report(report: dict) -> str:
    saturation = report["saturation_point"]
    lines = [
        f"# TinyTune saturation report: {report['run_label']}",
        "",
        f"Generated: {report['generated_at']}",
        "",
        f"Configuration: `{json.dumps(report['service_configuration'], sort_keys=True)}`",
        "",
        (
            f"Measured saturation point: **{saturation['target_rps']} target RPS** "
            f"({'; '.join(saturation['saturation_reasons'])})."
            if saturation
            else "No saturation threshold was crossed at the tested rates."
        ),
        "",
        "| Target RPS | Achieved RPS | p50 ms | p95 ms | p99 ms | Errors | Saturated |",
        "|---:|---:|---:|---:|---:|---:|:---:|",
    ]
    for result in report["steps"]:
        lines.append(
            f"| {result['target_rps']} | {result['achieved_rps']} | "
            f"{result['latency_ms']['p50']} | {result['latency_ms']['p95']} | "
            f"{result['latency_ms']['p99']} | {result['error_percent']}% | "
            f"{'yes' if result['saturated'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            "Saturation is the first step where p95 exceeds the configured latency limit, "
            "the error rate exceeds the configured limit, or achieved throughput falls below "
            "90% of the target arrival rate.",
            "",
        ]
    )
    return "\n".join(lines)


async def main() -> int:
    random.seed(1)
    limits = httpx.Limits(max_connections=1000, max_keepalive_connections=500)
    timeout = httpx.Timeout(8.0, connect=2.0)
    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        await wait_until_ready(client)
        playlist_id, track_id = await create_fixture(client)
        configuration = (await client.get(os.getenv("TOOLS_URL", "http://localhost:8081")+"/api/v1/ops/status")).json()
        print(f"TinyTune load test '{RUN_LABEL}': {configuration}", flush=True)
        steps = []
        for target_rps in STEP_RATES:
            result = await run_step(client, playlist_id, track_id, target_rps)
            steps.append(result)
            reasons = "; ".join(result["saturation_reasons"]) or "within thresholds"
            print(
                f"target={target_rps:>4} achieved={result['achieved_rps']:>7.2f} "
                f"p95={result['latency_ms']['p95']:>8.2f}ms "
                f"errors={result['error_percent']:>6.2f}% {reasons}",
                flush=True,
            )

    saturation_point = next((step for step in steps if step["saturated"]), None)
    report = {
        "run_label": RUN_LABEL,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_url": TARGET_URL,
        "service_configuration": configuration,
        "thresholds": {
            "p95_limit_ms": P95_LIMIT_MS,
            "error_limit_percent": ERROR_LIMIT_PERCENT,
            "minimum_achieved_ratio": 0.90,
        },
        "saturation_point": saturation_point,
        "steps": steps,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = f"{timestamp}-{RUN_LABEL}"
    json_path = RESULTS_DIR / f"{stem}.json"
    markdown_path = RESULTS_DIR / f"{stem}.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n")
    markdown_path.write_text(markdown_report(report))
    print(f"Reports written to {json_path} and {markdown_path}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(130)

