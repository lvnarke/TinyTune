"""Single local k6 executor; no Docker socket, shell commands or arbitrary targets."""

import asyncio
import json
import math
import os
import signal
import time
from collections import defaultdict
from contextlib import suppress
from pathlib import Path

from redis.asyncio import Redis

from .config import settings
from .web import LOAD_LOCK, LOAD_QUEUE, now


async def store(redis, job):
    await redis.set(f"tinytune:load:job:{job['id']}", json.dumps(job), ex=7 * 86400)


async def heartbeat(redis):
    while True:
        await redis.set("tinytune:load:heartbeat", "1", ex=6)
        await asyncio.sleep(2)


async def execute(redis, job):
    report_path = Path(f"/results/ui-{job['id']}.json")
    job.update(status="running", started_at=now())
    await store(redis, job)
    env = {**os.environ, "BASE_URL": "http://gateway:8080", "STEP_RATES": ",".join(map(str, job["rates"])),
           "STEP_DURATION_SECONDS": str(job["duration"]), "RUN_LABEL": f"ui-{job['id']}",
           "REPORT_PATH": str(report_path), "K6_NO_USAGE_REPORT": "true", "K6_LOG_OUTPUT": "none"}
    process = await asyncio.create_subprocess_exec(
        "k6", "run", "--quiet", "--out", "json=-", "/scripts/saturation.js",
        env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        limit=1024 * 1024,
    )
    start = time.monotonic()
    buckets = defaultdict(lambda: {"latencies": [], "failures": 0, "target": 0})
    errors = []

    async def read_output():
        async for line in process.stdout:
            try:
                item = json.loads(line)
                data = item.get("data", {})
                scenario = data.get("tags", {}).get("scenario", "")
                if item.get("type") != "Point" or not scenario.startswith("rate_"):
                    continue
                bucket = buckets[int(time.monotonic() - start)]
                bucket["target"] = int(scenario.removeprefix("rate_"))
                if item.get("metric") == "http_req_duration":
                    bucket["latencies"].append(data["value"])
                elif item.get("metric") == "http_req_failed":
                    bucket["failures"] += data["value"]
            except (ValueError, KeyError, TypeError):
                continue

    async def read_errors():
        async for line in process.stderr:
            errors.append(line.decode(errors="replace")[:500])
            del errors[:-10]

    output = asyncio.create_task(read_output())
    stderr = asyncio.create_task(read_errors())
    cancelled = False
    try:
        while process.returncode is None:
            elapsed = time.monotonic() - start
            if await redis.get(f"tinytune:load:cancel:{job['id']}"):
                cancelled = True
                process.send_signal(signal.SIGINT)
                break
            if elapsed > job["estimated_seconds"] + 60:
                process.kill()
                job["error"] = "Experiment exceeded its execution deadline"
                break
            samples = []
            for second in sorted(buckets):
                if second >= int(elapsed):
                    continue
                values = buckets[second]
                durations = sorted(values["latencies"])
                if durations:
                    samples.append({"second": second, "rps": len(durations), "target": values["target"],
                                    "p95_ms": round(durations[min(len(durations)-1, math.ceil(len(durations)*.95)-1)], 2),
                                    "error_percent": round(100*values["failures"]/len(durations), 2)})
            job.update(samples=samples, elapsed_seconds=round(elapsed))
            await store(redis, job)
            await asyncio.sleep(1)
        try:
            await asyncio.wait_for(process.wait(), timeout=10)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
        await output
        await stderr
        if report_path.exists():
            job["report"] = json.loads(report_path.read_text())
        job["status"] = "cancelled" if cancelled else "completed" if process.returncode == 0 and job["report"] else "failed"
        if job["status"] == "failed" and not job["error"]:
            job["error"] = "".join(errors)[-1800:] or "k6 did not produce a report"
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
        output.cancel()
        stderr.cancel()
        job["finished_at"] = now()
        await store(redis, job)


async def main():
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    # A runner restart must not leave a running job or a global admission lock stuck.
    active = await redis.get(LOAD_LOCK)
    if active:
        raw = await redis.get(f"tinytune:load:job:{active}")
        if raw:
            job = json.loads(raw)
            if job["status"] == "running":
                job.update(status="failed", error="Load runner restarted during this experiment", finished_at=now())
                await store(redis, job)
                await redis.delete(LOAD_LOCK)
    pulse = asyncio.create_task(heartbeat(redis))
    print("TinyTune load runner ready", flush=True)
    try:
        while True:
            item = await redis.blpop(LOAD_QUEUE, timeout=2)
            if not item:
                continue
            job_id = item[1]
            raw = await redis.get(f"tinytune:load:job:{job_id}")
            if not raw:
                continue
            job = json.loads(raw)
            if job["status"] != "queued":
                continue
            try:
                if await redis.get(f"tinytune:load:cancel:{job_id}"):
                    job.update(status="cancelled", finished_at=now())
                    await store(redis, job)
                else:
                    await execute(redis, job)
            except Exception as exc:
                job.update(status="failed", error=str(exc)[:1000], finished_at=now())
                await store(redis, job)
            finally:
                await redis.eval("if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) end return 0", 1, LOAD_LOCK, job_id)
    finally:
        pulse.cancel()
        with suppress(asyncio.CancelledError):
            await pulse
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
