"""Browser identity, personal library and a bounded, local-only load control plane."""

import asyncio
import hashlib
import json
import os
import secrets
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from pydantic import BaseModel, Field
import asyncpg
from typing import Literal
from .access import playlist_role, require_tools

router = APIRouter()
COOKIE = "tinytune_session"
SESSION_PREFIX = "tinytune:session:v2:"
SESSION_TTL = 7 * 86400
LOAD_LOCK = "tinytune:load:active"
LOAD_QUEUE = "tinytune:load:queue"


def now():
    return datetime.now(timezone.utc).isoformat()


def browser_write(request: Request):
    if request.headers.get("X-TinyTune-Request") != "1":
        raise HTTPException(403, "Missing browser request header")


async def current_user(request: Request, required: bool = True):
    if hasattr(request.state, "identity"):
        user = request.state.identity
        if not user and required:
            raise HTTPException(401, "Please sign in to continue")
        return user
    token = request.cookies.get(COOKIE)
    raw = await request.app.state.redis.get(
        f"{SESSION_PREFIX}{hashlib.sha256(token.encode()).hexdigest()}"
    ) if token else None
    if not raw and required:
        raise HTTPException(401, "Please sign in to continue")
    request.state.identity = json.loads(raw) if raw else None
    return request.state.identity


async def start_session(request: Request, response: Response, user: dict):
    old = request.cookies.get(COOKIE)
    if old:
        await request.app.state.redis.delete(f"{SESSION_PREFIX}{hashlib.sha256(old.encode()).hexdigest()}")
    token = secrets.token_urlsafe(32)
    await request.app.state.redis.set(
        f"{SESSION_PREFIX}{hashlib.sha256(token.encode()).hexdigest()}",
        json.dumps(user), ex=SESSION_TTL,
    )
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax",
                        secure=os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true",
                        max_age=SESSION_TTL, path="/")


@router.get("/auth/config")
async def auth_config(request: Request, response: Response):
    nonce = secrets.token_urlsafe(32)
    await request.app.state.redis.set(f"tinytune:nonce:{nonce}", "1", ex=600)
    response.set_cookie("tinytune_nonce", nonce, httponly=True, samesite="lax", max_age=600,
                        secure=os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true")
    response.headers["Cache-Control"] = "no-store"
    return {"google_client_id": os.getenv("GOOGLE_CLIENT_ID", ""), "nonce": nonce,
            "demo_enabled": False, "local_enabled": True}


def hash_password(password: str, salt: str | None = None):
    salt = salt or secrets.token_hex(16)
    derived = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768, r=8, p=3,
                             maxmem=64*1024*1024, dklen=32)
    return f"scrypt${salt}${derived.hex()}"


def check_password(password: str, stored: str | None):
    # Do equivalent work for unknown usernames to avoid a cheap account timing oracle.
    if not stored:
        hash_password(password, "00"*16)
        return False
    try:
        _, salt, _ = stored.split("$")
        return secrets.compare_digest(hash_password(password, salt), stored)
    except (ValueError, TypeError):
        return False


async def limit_login(request: Request, username: str):
    redis = request.app.state.redis
    digest = hashlib.sha256(username.lower().encode()).hexdigest()
    address = request.headers.get("X-Real-IP") or (request.client.host if request.client else "local")
    for key, limit in [(f"tinytune:auth:account:{digest}", 20),
                       (f"tinytune:auth:ip:{address}", 150)]:
        async with redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, 60)
            count, _ = await pipe.execute()
        if count > limit:
            raise HTTPException(429, "Too many sign-in attempts. Please try again in a minute.")


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z][a-zA-Z0-9_]{2,31}$")
    password: str = Field(min_length=1, max_length=128)


class Registration(Credentials):
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=12, max_length=128)


@router.post("/auth/signup", status_code=201)
async def signup(payload: Registration, request: Request, response: Response):
    browser_write(request)
    await limit_login(request, payload.username)
    username = payload.username.lower()
    if username.startswith(("g_", "user_")):
        raise HTTPException(422, "That username prefix is reserved. Please choose another.")
    encoded = await asyncio.to_thread(hash_password, payload.password)
    try:
        async with request.app.state.pool.acquire(timeout=1) as connection:
            row = await connection.fetchrow("""INSERT INTO app_users(id,provider,provider_id,name,username,password_hash)
                VALUES($1,'local',$2,$3,$2,$4) RETURNING id,provider,name,email,picture,username""",
                uuid4(), username, payload.name.strip() or username, encoded)
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(409, "That username is taken. Try another.") from exc
    user = dict(row)
    user["id"] = str(user["id"])
    await start_session(request, response, user)
    return {"user": user}


@router.post("/auth/login")
async def login(payload: Credentials, request: Request, response: Response):
    browser_write(request)
    await limit_login(request, payload.username)
    async with request.app.state.pool.acquire(timeout=1) as connection:
        row = await connection.fetchrow("SELECT id,provider,name,email,picture,username,password_hash FROM app_users WHERE lower(username)=$1 AND provider='local'", payload.username.lower())
    valid = await asyncio.to_thread(check_password, payload.password, row["password_hash"] if row else None)
    if not valid:
        raise HTTPException(401, "Incorrect username or password")
    user = {k: v for k, v in dict(row).items() if k != "password_hash"}
    user["id"] = str(user["id"])
    await start_session(request, response, user)
    return {"user": user}


class GoogleLogin(BaseModel):
    credential: str = Field(min_length=10, max_length=12000)


@router.post("/auth/google")
async def google_login(payload: GoogleLogin, request: Request, response: Response):
    browser_write(request)
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        raise HTTPException(503, "Google sign-in needs GOOGLE_CLIENT_ID in .env")
    try:
        claims = await asyncio.wait_for(asyncio.to_thread(
            id_token.verify_oauth2_token, payload.credential, GoogleRequest(), client_id
        ), timeout=10)
    except ValueError as exc:
        raise HTTPException(401, "Google could not verify this sign-in. Please try again.") from exc
    except Exception as exc:
        raise HTTPException(503, "Google verification is temporarily unavailable. Please try again.") from exc
    nonce = request.cookies.get("tinytune_nonce")
    if not nonce or not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise HTTPException(401, "Sign-in challenge expired. Refresh and try again.")
    if not await request.app.state.redis.getdel(f"tinytune:nonce:{nonce}"):
        raise HTTPException(401, "Sign-in challenge already used or expired")
    if not claims.get("email_verified") or not claims.get("sub"):
        raise HTTPException(401, "A verified Google account is required")
    async with request.app.state.pool.acquire(timeout=1) as connection:
        row = await connection.fetchrow(
            """INSERT INTO app_users(id,provider,provider_id,name,email,picture,username)
            VALUES($1,'google',$2,$3,$4,$5,$6)
            ON CONFLICT(provider,provider_id) DO UPDATE
            SET name=EXCLUDED.name,email=EXCLUDED.email,picture=EXCLUDED.picture
            RETURNING id,provider,name,email,picture,username""",
            uuid4(), claims["sub"], claims.get("name", "Music lover"),
            claims.get("email"), claims.get("picture"),
            "g_" + hashlib.sha256(claims["sub"].encode()).hexdigest()[:24],
        )
    user = dict(row)
    user["id"] = str(user["id"])
    await start_session(request, response, user)
    response.delete_cookie("tinytune_nonce")
    return {"user": user}


@router.post("/auth/demo")
async def demo_login(request: Request, response: Response):
    raise HTTPException(410, "Demo bypass has been removed. Create an account or sign in.")


@router.get("/auth/me")
async def me(request: Request):
    return {"user": await current_user(request, required=False)}


@router.post("/auth/logout")
async def logout(request: Request, response: Response):
    browser_write(request)
    token = request.cookies.get(COOKIE)
    if token:
        await request.app.state.redis.delete(f"{SESSION_PREFIX}{hashlib.sha256(token.encode()).hexdigest()}")
    response.delete_cookie(COOKIE)
    return {"ok": True}


STARTER_PLAYLISTS = [
    ("After hours", "For the hours that belong to you. Soft edges, late nights.", 0,
     [("Midnight City", "M83"), ("Nightcall", "Kavinsky"), ("Intro", "The xx"), ("Retrograde", "James Blake")]),
    ("A little more focus", "Clear your desk. Quiet your mind. Find your flow.", 1,
     [("Weightless", "Marconi Union"), ("A Walk", "Tycho"), ("First Breath After Coma", "Explosions in the Sky")]),
    ("Sunday kind of love", "Slow mornings and nowhere in particular to be.", 2,
     [("Pink + White", "Frank Ocean"), ("Show Me How", "Men I Trust"), ("Coming Home", "Leon Bridges")]),
    ("Out of office", "Take the long way. Windows down. Volume up.", 3,
     [("Tadow", "Masego & FKJ"), ("Tieduprightnow", "Parcels"), ("Texas Sun", "Khruangbin & Leon Bridges")]),
]


@router.post("/api/v1/library/initialize")
async def initialize_library(request: Request):
    browser_write(request)
    user = await current_user(request)
    async with request.app.state.pool.acquire(timeout=1) as connection:
        async with connection.transaction():
            initialized = await connection.fetchval(
                "SELECT library_initialized FROM app_users WHERE id=$1 FOR UPDATE", UUID(user["id"]))
            if not initialized:
                for name, description, cover, tracks in STARTER_PLAYLISTS:
                    pid = uuid4()
                    await connection.execute("INSERT INTO playlists(id,name,owner_id,description,cover) VALUES($1,$2,$3,$4,$5)",
                                             pid, name, UUID(user["id"]), description, cover)
                    await connection.executemany("INSERT INTO tracks(id,playlist_id,title,artist,position) VALUES($1,$2,$3,$4,$5)",
                                                 [(uuid4(), pid, t, a, i + 1) for i, (t, a) in enumerate(tracks)])
                await connection.execute("UPDATE app_users SET library_initialized=TRUE WHERE id=$1", UUID(user["id"]))
    return {"ok": True}


@router.get("/api/v1/library")
async def library(request: Request):
    user = await current_user(request)
    async with request.app.state.pool.acquire(timeout=1) as connection:
        rows = await connection.fetch("""SELECT p.id,p.name,p.description,p.cover,p.created_at,
            CASE WHEN p.owner_id=$1 THEN 'owner' ELSE m.role END AS role,
            (f.user_id IS NOT NULL) AS favorite,u.name AS owner_name,u.username AS owner_username,
            COUNT(t.id)::int AS track_count,COALESCE(SUM(c.play_count),0)::bigint AS play_count
            FROM playlists p LEFT JOIN tracks t ON t.playlist_id=p.id
            LEFT JOIN track_play_counts c ON c.track_id=t.id
            LEFT JOIN playlist_members m ON m.playlist_id=p.id AND m.user_id=$1
            LEFT JOIN playlist_favorites f ON f.playlist_id=p.id AND f.user_id=$1
            JOIN app_users u ON u.id=p.owner_id
            WHERE p.owner_id=$1 OR m.user_id=$1
            GROUP BY p.id,m.role,f.user_id,u.name,u.username ORDER BY p.created_at DESC""", UUID(user["id"]))
    return {"playlists": [dict(row) for row in rows]}


class Favorite(BaseModel):
    favorite: bool


@router.patch("/api/v1/library/{playlist_id}")
async def favorite(playlist_id: UUID, payload: Favorite, request: Request):
    browser_write(request)
    user = await current_user(request)
    async with request.app.state.pool.acquire(timeout=1) as connection:
        async with connection.transaction():
            await playlist_role(connection, playlist_id, UUID(user["id"]), lock=True)
            if payload.favorite:
                await connection.execute("INSERT INTO playlist_favorites(playlist_id,user_id) VALUES($1,$2) ON CONFLICT DO NOTHING", playlist_id, UUID(user["id"]))
            else:
                await connection.execute("DELETE FROM playlist_favorites WHERE playlist_id=$1 AND user_id=$2", playlist_id, UUID(user["id"]))
    return {"ok": True}


class ShareGrant(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    role: Literal["viewer", "editor"] = "viewer"


@router.get("/api/v1/playlists/{playlist_id}/sharing")
async def sharing(playlist_id: UUID, request: Request):
    user = await current_user(request)
    async with request.app.state.pool.acquire(timeout=1) as connection:
        await playlist_role(connection, playlist_id, UUID(user["id"]), owner=True)
        rows = await connection.fetch("""SELECT u.id AS user_id,u.name,u.username,m.role FROM playlist_members m
            JOIN app_users u ON u.id=m.user_id WHERE m.playlist_id=$1 ORDER BY m.created_at""", playlist_id)
    return {"members": [dict(row) for row in rows], "visibility": "private"}


@router.post("/api/v1/playlists/{playlist_id}/sharing")
async def grant_access(playlist_id: UUID, payload: ShareGrant, request: Request):
    browser_write(request)
    user = await current_user(request)
    async with request.app.state.pool.acquire(timeout=1) as connection:
        async with connection.transaction():
            await playlist_role(connection, playlist_id, UUID(user["id"]), owner=True, lock=True)
            recipient = await connection.fetchrow("SELECT id,name,username FROM app_users WHERE lower(username)=$1 AND provider IN ('local','google')", payload.username.strip().lower().removeprefix("@"))
            if not recipient:
                raise HTTPException(404, "No account with that username. Ask them to sign up first.")
            if str(recipient["id"]) == user["id"]:
                raise HTTPException(422, "You already own this playlist")
            await connection.execute("""INSERT INTO playlist_members(playlist_id,user_id,role) VALUES($1,$2,$3)
                ON CONFLICT(playlist_id,user_id) DO UPDATE SET role=EXCLUDED.role""", playlist_id, recipient["id"], payload.role)
    return {"user_id": str(recipient["id"]), "name": recipient["name"], "username": recipient["username"], "role": payload.role}


@router.delete("/api/v1/playlists/{playlist_id}/sharing/{member_id}")
async def revoke_access(playlist_id: UUID, member_id: UUID, request: Request):
    browser_write(request)
    user = await current_user(request)
    async with request.app.state.pool.acquire(timeout=1) as connection:
        async with connection.transaction():
            await playlist_role(connection, playlist_id, UUID(user["id"]), owner=True, lock=True)
            await connection.execute("DELETE FROM playlist_members WHERE playlist_id=$1 AND user_id=$2", playlist_id, member_id)
            await connection.execute("DELETE FROM playlist_favorites WHERE playlist_id=$1 AND user_id=$2", playlist_id, member_id)
    return {"ok": True}


class LoadSpec(BaseModel):
    name: str = Field(default="Untitled experiment", min_length=1, max_length=80)
    rates: list[int] = Field(default=[50, 100, 200], min_length=1, max_length=5)
    duration: int = Field(default=10, ge=5, le=60)


@router.post("/api/v1/load-tests", status_code=202)
async def create_load(payload: LoadSpec, request: Request):
    browser_write(request)
    require_tools(request)
    user = {"id": "local-tools"}
    if any(rate < 1 or rate > 3000 for rate in payload.rates):
        raise HTTPException(422, "Each arrival rate must be between 1 and 3,000 RPS")
    if any(current <= previous for previous, current in zip(payload.rates, payload.rates[1:])):
        raise HTTPException(422, "Arrival rates must increase at each step")
    redis = request.app.state.redis
    if not await redis.get("tinytune:load:heartbeat"):
        raise HTTPException(503, "Load runner is offline. Start the load-runner Compose service.")
    job_id = str(uuid4())
    if not await redis.set(LOAD_LOCK, job_id, nx=True, ex=900):
        raise HTTPException(409, "Another experiment is running. Wait for it to finish.")
    job = {"id": job_id, "owner_id": user["id"], "name": payload.name,
           "rates": payload.rates, "duration": payload.duration, "status": "queued",
           "created_at": now(), "samples": [], "report": None, "error": None,
           "estimated_seconds": 5 + len(payload.rates) * (payload.duration + 2)}
    try:
        async with redis.pipeline(transaction=True) as pipe:
            pipe.set(f"tinytune:load:job:{job_id}", json.dumps(job), ex=7 * 86400)
            pipe.lpush(f"tinytune:load:history:{user['id']}", job_id)
            pipe.ltrim(f"tinytune:load:history:{user['id']}", 0, 29)
            pipe.rpush(LOAD_QUEUE, job_id)
            await pipe.execute()
    except Exception:
        await redis.delete(LOAD_LOCK)
        raise
    return job


@router.get("/api/v1/load-tests")
async def load_history(request: Request):
    require_tools(request)
    user = {"id": "local-tools"}
    redis = request.app.state.redis
    ids = await redis.lrange(f"tinytune:load:history:{user['id']}", 0, 29)
    jobs = await redis.mget([f"tinytune:load:job:{i}" for i in ids]) if ids else []
    return {"runs": [json.loads(raw) for raw in jobs if raw]}


async def owned_job(job_id: UUID, request: Request):
    require_tools(request)
    raw = await request.app.state.redis.get(f"tinytune:load:job:{job_id}")
    job = json.loads(raw) if raw else None
    if not job or job["owner_id"] != "local-tools":
        raise HTTPException(404, "Experiment not found")
    return job


@router.get("/api/v1/load-tests/{job_id}")
async def get_load(job_id: UUID, request: Request):
    return await owned_job(job_id, request)


@router.post("/api/v1/load-tests/{job_id}/cancel")
async def cancel_load(job_id: UUID, request: Request):
    browser_write(request)
    job = await owned_job(job_id, request)
    if job["status"] in {"queued", "running"}:
        await request.app.state.redis.set(f"tinytune:load:cancel:{job_id}", "1", ex=900)
    return {"ok": True}


@router.get("/api/v1/load-tests/{job_id}/download")
async def download_load(job_id: UUID, request: Request):
    job = await owned_job(job_id, request)
    if not job.get("report"):
        raise HTTPException(409, "The report is not ready yet")
    return Response(json.dumps(job["report"], indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="tinytune-{job_id}.json"'})


PROM_QUERIES = {
    "request_rate": 'sum(rate(tinytune_http_requests_total{route!~"/metrics|/health/.*|/api/v1/console|/auth/.*"}[30s]))',
    "p95_ms": '1000*histogram_quantile(0.95,sum(rate(tinytune_http_request_duration_seconds_bucket{route!~"/metrics|/health/.*|/api/v1/console|/auth/.*"}[30s])) by(le))',
    "error_percent": '100*(sum(rate(tinytune_http_requests_total{status=~"5.."}[30s])) or vector(0))/clamp_min(sum(rate(tinytune_http_requests_total[30s])),0.001)',
    "worker_rate": 'sum(rate(tinytune_worker_events_total{result="processed"}[30s]))',
    "api_replicas": 'count((up{job="tinytune-api"} == 1) and (timestamp(up{job="tinytune-api"}) > time()-10)) or vector(0)',
    "worker_replicas": 'count((up{job="tinytune-worker"} == 1) and (timestamp(up{job="tinytune-worker"}) > time()-10)) or vector(0)',
    "cache_hit_percent": '100*sum(rate(tinytune_cache_operations_total{result="hit"}[30s]))/clamp_min(sum(rate(tinytune_cache_operations_total{result=~"hit|miss"}[30s])),0.001)',
}


@router.get("/api/v1/console")
async def console_status(request: Request):
    require_tools(request)
    redis = request.app.state.redis
    async def query(client, name, expression):
        try:
            response = await client.get("http://prometheus:9090/api/v1/query", params={"query": expression})
            response.raise_for_status()
            rows = response.json()["data"]["result"]
            value = float(rows[0]["value"][1]) if rows else None
            return name, value if value is not None and value == value and abs(value) != float("inf") else None
        except Exception:
            return name, None
    async with httpx.AsyncClient(timeout=2) as client:
        values = dict(await asyncio.gather(*(query(client, k, v) for k, v in PROM_QUERIES.items())))
    values.update({"timestamp": time.time(), "queue_depth": await redis.xlen("tinytune:play-events"),
                   "runner_online": bool(await redis.get("tinytune:load:heartbeat")),
                   "active_job_id": await redis.get(LOAD_LOCK)})
    return values
