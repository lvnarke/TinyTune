"""Small end-to-end product demonstration using only the public API."""

import json
import os
import time
import secrets

import httpx


base_url = os.getenv("TARGET_URL", "http://localhost:8080").rstrip("/")


def show(label: str, response: httpx.Response) -> dict:
    response.raise_for_status()
    body = response.json()
    print(f"\n{label} [{response.status_code}]")
    print(json.dumps(body, indent=2))
    return body


with httpx.Client(base_url=base_url, timeout=10, headers={"X-TinyTune-Request":"1"}) as client:
    signup = client.post("/auth/signup", json={"username":"demo_" + secrets.token_hex(6), "name":"CLI demo listener", "password":secrets.token_urlsafe(24)})
    signup.raise_for_status()
    playlist = show(
        "Created playlist",
        client.post("/api/v1/playlists", json={"name": "Distributed Beats"}),
    )
    playlist_id = playlist["id"]
    track = show(
        "Added track",
        client.post(
            f"/api/v1/playlists/{playlist_id}/tracks",
            json={"title": "Eventually Consistent", "artist": "The Replicas"},
        ),
    )
    show("Read playlist", client.get(f"/api/v1/playlists/{playlist_id}"))
    for index in range(3):
        show(
            f"Accepted play {index + 1}",
            client.post(
                f"/api/v1/playlists/{playlist_id}/plays",
                headers={"Idempotency-Key": f"demo-{playlist_id}-{index}"},
                json={"track_id": track["id"]},
            ),
        )
    show(
        "Retried third play with the same idempotency key",
        client.post(
            f"/api/v1/playlists/{playlist_id}/plays",
            headers={"Idempotency-Key": f"demo-{playlist_id}-2"},
            json={"track_id": track["id"]},
        ),
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        stats = client.get(f"/api/v1/playlists/{playlist_id}/stats")
        ops = httpx.get(os.getenv("TOOLS_URL", "http://localhost:8081") + "/api/v1/ops/status").json()
        if stats.json()["tracks"][0]["play_count"] == 3 and ops["queue_depth"] == 0:
            show("Eventually consistent statistics", stats)
            break
        time.sleep(0.2)
    else:
        raise RuntimeError("worker did not idempotently process the plays within 10 seconds")
    show("Operational status", httpx.get(os.getenv("TOOLS_URL", "http://localhost:8081") + "/api/v1/ops/status"))

