"""Real HTTP checks for private playlists, role isolation and the separate local lab."""

import os
import secrets
import time
from contextlib import ExitStack

import httpx

BASE = os.getenv("TARGET_URL", "http://gateway:8080")
TOOLS = os.getenv("TOOLS_URL", "http://gateway:8081")
DOCS = os.getenv("DOCS_URL", "http://gateway:8082")
HEADERS = {"X-TinyTune-Request": "1"}


def expect(response, status=200):
    assert response.status_code == status, (response.status_code, response.text)
    return response.json() if "json" in response.headers.get("content-type", "") else response.text


with ExitStack() as stack:
    clients = [stack.enter_context(httpx.Client(base_url=BASE, headers=HEADERS, timeout=15)) for _ in range(5)]
    alice, bob, editor, charlie, guest = clients
    lab = stack.enter_context(httpx.Client(base_url=TOOLS, headers=HEADERS, timeout=10))
    users = []
    for name, client in zip(["Alice", "Bob", "Editor", "Charlie"], clients):
        username = "test_"+secrets.token_hex(6)
        password = secrets.token_urlsafe(24)
        auth = client.post("/auth/signup", json={"name": name,"username":username,"password":password})
        user = expect(auth, 201)["user"]
        users.append(user)
        assert "password" not in str(user)
        assert "httponly" in auth.headers["set-cookie"].lower()
        expect(client.post("/auth/logout"))
        expect(client.post("/auth/login", json={"username":username,"password":"wrong-password"}), 401)
        expect(client.post("/auth/login", json={"username":username.upper(),"password":password}))
        expect(guest.post("/auth/signup",json={"name":"Duplicate","username":username,"password":password}),409)
    expect(guest.post("/auth/signup",json={"name":"Short","username":"short_password_test","password":"short"}),422)
    expect(guest.post("/auth/demo"),410)
    expect(guest.post("/auth/login",headers={"Origin":"https://untrusted.example"},json={"username":"alice","password":"secret"}),403)
    assert expect(alice.get("/api/v1/library"))["playlists"] == []
    for _ in range(8):
        assert expect(alice.get("/auth/me"))["user"]["id"] == users[0]["id"]
    playlist = expect(alice.post("/api/v1/playlists",json={"name":"Alice's private mix","description":"Permission verification","cover":3}),201)
    pid = playlist["id"]
    track = expect(alice.post(f"/api/v1/playlists/{pid}/tracks",json={"title":"Private song","artist":"Permission tests"}),201)
    tid = track["id"]
    for client, status in [(guest,401),(bob,404),(charlie,404)]:
        expect(client.get(f"/api/v1/playlists/{pid}"),status)
        expect(client.get(f"/api/v1/playlists/{pid}/stats"),status)
        expect(client.post(f"/api/v1/playlists/{pid}/plays",json={"track_id":tid}),status)
        expect(client.post(f"/api/v1/playlists/{pid}/tracks",json={"title":"Unauthorized","artist":"No"}),status)
        expect(client.get(f"/api/v1/playlists/{pid}/sharing"),status)
    expect(guest.post("/api/v1/playlists",json={"name":"Anonymous"}),401)
    assert expect(charlie.get("/api/v1/library"))["playlists"] == []
    expect(alice.post(f"/api/v1/playlists/{pid}/sharing",json={"username":users[1]["username"],"role":"viewer"}))
    expect(alice.post(f"/api/v1/playlists/{pid}/sharing",json={"username":users[2]["username"],"role":"editor"}))
    expect(alice.post(f"/api/v1/playlists/{pid}/sharing",json={"username":users[3]["username"],"role":"owner"}),422)
    assert expect(bob.get(f"/api/v1/playlists/{pid}"))["role"] == "viewer"
    assert expect(editor.get(f"/api/v1/playlists/{pid}"))["role"] == "editor"
    assert expect(alice.get(f"/api/v1/playlists/{pid}"))["role"] == "owner"
    assert expect(bob.get("/api/v1/library"))["playlists"][0]["role"] == "viewer"
    expect(bob.post(f"/api/v1/playlists/{pid}/tracks",json={"title":"Cannot add","artist":"Viewer"}),403)
    expect(editor.post(f"/api/v1/playlists/{pid}/tracks",json={"title":"Can add","artist":"Editor"}),201)
    for client in [bob,editor]:
        expect(client.get(f"/api/v1/playlists/{pid}/sharing"),403)
        expect(client.post(f"/api/v1/playlists/{pid}/sharing",json={"username":users[3]["username"],"role":"viewer"}),403)
        expect(client.delete(f"/api/v1/playlists/{pid}/sharing/{users[1]['id']}"),403)
    expect(bob.patch(f"/api/v1/library/{pid}",json={"favorite":True}))
    assert expect(bob.get("/api/v1/library"))["playlists"][0]["favorite"]
    assert not expect(alice.get("/api/v1/library"))["playlists"][0]["favorite"]
    key=secrets.token_hex(10)
    for _ in range(2):
        expect(bob.post(f"/api/v1/playlists/{pid}/plays",headers={"Idempotency-Key":key},json={"track_id":tid}),202)
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        stats=expect(bob.get(f"/api/v1/playlists/{pid}/stats"))
        if stats["tracks"][0]["play_count"]==1:break
        time.sleep(.2)
    assert stats["tracks"][0]["play_count"]==1
    # Warm the shared content cache before revocation. ACL must still be checked.
    expect(bob.get(f"/api/v1/playlists/{pid}"))
    expect(alice.delete(f"/api/v1/playlists/{pid}/sharing/{users[1]['id']}"))
    for _ in range(6):
        expect(bob.get(f"/api/v1/playlists/{pid}"),404)
    expect(bob.get(f"/api/v1/playlists/{pid}/stats"),404)
    expect(bob.post(f"/api/v1/playlists/{pid}/plays",json={"track_id":tid}),404)
    expect(bob.patch(f"/api/v1/library/{pid}",json={"favorite":True}),404)
    assert expect(bob.get("/api/v1/library"))["playlists"]==[]
    expect(editor.get(f"/api/v1/playlists/{pid}"))
    expect(alice.post(f"/api/v1/playlists/{pid}/sharing",json={"username":users[2]["username"],"role":"viewer"}))
    expect(editor.post(f"/api/v1/playlists/{pid}/tracks",json={"title":"Downgraded","artist":"No"}),403)
    # Header spoofing cannot turn the customer listener into a tools listener.
    expect(alice.get("/api/v1/console",headers={"X-TinyTune-Surface":"tools"}),404)
    expect(guest.get("/api/v1/load-tests"),404)
    expect(guest.get("/docs"),404)
    expect(lab.get("/auth/me"),404)
    expect(lab.get(f"/api/v1/playlists/{pid}"),404)
    expect(lab.get("/api/v1/library"),404)
    assert httpx.get(DOCS+"/docs").status_code==200
    assert httpx.get(DOCS+"/api/v1/library").status_code==404
    expect(lab.post("/api/v1/load-tests",json={"rates":[99999]}),422)
    job=expect(lab.post("/api/v1/load-tests",json={"name":"Private fixture verification","rates":[10,20],"duration":5}),202)
    jid=job["id"]
    expect(lab.post("/api/v1/load-tests",json={"rates":[10]}),409)
    deadline=time.monotonic()+65
    saw_samples=False
    while time.monotonic()<deadline:
        job=expect(lab.get(f"/api/v1/load-tests/{jid}"))
        saw_samples|=bool(job["samples"])
        if job["status"] not in {"queued","running"}:break
        time.sleep(1)
    assert job["status"]=="completed",job
    assert saw_samples and len(job["report"]["steps"])==2
    assert all(s["error_percent"]==0 for s in job["report"]["steps"]),job["report"]
    expect(lab.get(f"/api/v1/load-tests/{jid}/download"))
    cancelled=expect(lab.post("/api/v1/load-tests",json={"name":"Cancellation check","rates":[10],"duration":30}),202)
    expect(lab.post(f"/api/v1/load-tests/{cancelled['id']}/cancel"))
    for _ in range(15):
        result=expect(lab.get(f"/api/v1/load-tests/{cancelled['id']}"))
        if result["status"]=="cancelled":break
        time.sleep(1)
    assert result["status"]=="cancelled",result
    assert expect(lab.get("/api/v1/console"))["runner_online"]
    expect(alice.post("/auth/logout"))
    expect(alice.get(f"/api/v1/playlists/{pid}"),401)
    print("PASS: local registration/login, shared sessions, private reads/counts/plays, owner/editor/viewer roles,")
    print("      scoped favorites, cached-content revocation, role downgrade, isolated tools/docs, real authenticated k6,")
    print("      live samples, admission limit, report export, cancellation and logout")
