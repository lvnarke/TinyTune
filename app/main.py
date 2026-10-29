import asyncio
import hashlib
import json
import logging
import os
import time
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from typing import Annotated, AsyncIterator
from uuid import UUID, uuid4
from pathlib import Path

import asyncpg
from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.asyncio import Redis
from redis.exceptions import RedisError, ResponseError
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.openapi.docs import get_swagger_ui_html

from .config import settings
from .db import create_pool
from .logging_config import configure_logging
from .web import router as web_router, current_user
from .access import playlist_role, require_tools
from .metrics import (
    CACHE_OPERATIONS,
    DB_POOL_TIMEOUTS,
    HTTP_DURATION,
    HTTP_IN_PROGRESS,
    HTTP_REQUESTS,
    PLAY_EVENTS_ENQUEUED,
    PLAY_EVENTS_SYNC,
    QUEUE_DEPTH,
)


configure_logging(settings.log_level)
logger = logging.getLogger("tinytune.api")


class PlaylistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    cover: int = Field(default=0, ge=0, le=5)


class TrackCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    artist: str = Field(min_length=1, max_length=200)


class PlayCreate(BaseModel):
    track_id: UUID


async def _ensure_consumer_group(redis: Redis) -> None:
    try:
        await redis.xgroup_create(
            settings.stream_name, settings.consumer_group, id="0-0", mkstream=True
        )
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def _queue_depth_loop(redis: Redis) -> None:
    while True:
        try:
            QUEUE_DEPTH.set(await redis.xlen(settings.stream_name))
        except RedisError:
            logger.warning("queue depth collection failed", exc_info=True)
        await asyncio.sleep(2)


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await create_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock(7419082)")
            await connection.execute((Path(__file__).parent.parent / "db/002-web.sql").read_text())
            await connection.execute((Path(__file__).parent.parent / "db/003-permissions.sql").read_text())
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    await redis.ping()
    await _ensure_consumer_group(redis)
    app.state.pool = pool
    app.state.redis = redis
    queue_task = asyncio.create_task(_queue_depth_loop(redis))
    logger.info(
        "api started",
        extra={
            "fields": {
                "play_mode": settings.play_mode,
                "cache_enabled": settings.cache_enabled,
                "db_pool_size": settings.db_pool_size,
            }
        },
    )
    try:
        yield
    finally:
        queue_task.cancel()
        with suppress(asyncio.CancelledError):
            await queue_task
        await redis.aclose()
        await pool.close()
        logger.info("api stopped")


app = FastAPI(
    title="TinyTune",
    version="1.2.0",
    docs_url=None, redoc_url=None, openapi_url=None,
    description="A locally runnable distributed playlist and play-analytics service.",
    lifespan=lifespan,
)
app.include_router(web_router)


@app.middleware("http")
async def browser_security(request: Request, call_next):
    surface = request.headers.get("X-TinyTune-Surface", "customer")
    path = request.url.path
    if surface == "tools" and (path.startswith("/auth/") or path.startswith("/api/v1/playlists") or path.startswith("/api/v1/library")):
        return JSONResponse({"detail": "Customer data is not available in the load lab"}, status_code=404)
    if surface == "customer" and (path.startswith(("/api/v1/load-tests", "/api/v1/console", "/api/v1/ops")) or path in {"/console", "/docs", "/openapi.json"}):
        return JSONResponse({"detail": "Not found"}, status_code=404)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        expected_origin = os.getenv("TOOLS_ORIGIN", "http://localhost:8081") if surface == "tools" else os.getenv("APP_ORIGIN", "http://localhost:8080")
        if origin and origin != expected_origin:
            return JSONResponse({"detail": "Cross-origin request rejected"}, status_code=403)
    if path.startswith(("/api/v1/playlists", "/api/v1/library")):
        try:
            await current_user(request)
            if request.method not in {"GET", "HEAD"} and request.headers.get("X-TinyTune-Request") != "1":
                return JSONResponse({"detail": "Missing browser request header"}, status_code=403)
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
    if request.url.path.startswith(("/auth/", "/api/")):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.middleware("http")
async def observe_requests(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = request_id
    started = time.perf_counter()
    status_code = 500
    response = None
    HTTP_IN_PROGRESS.labels(request.method).inc()
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        elapsed = time.perf_counter() - started
        route = request.scope.get("route")
        route_name = getattr(route, "path", request.url.path)
        HTTP_IN_PROGRESS.labels(request.method).dec()
        HTTP_REQUESTS.labels(request.method, route_name, str(status_code)).inc()
        HTTP_DURATION.labels(request.method, route_name).observe(elapsed)
        sample_bucket = int(hashlib.sha256(request_id.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
        if (
            status_code >= 500
            or elapsed >= 0.25
            or sample_bucket < settings.success_log_sample_rate
        ):
            logger.info(
                "request completed",
                extra={
                    "fields": {
                        "request_id": request_id,
                        "method": request.method,
                        "route": route_name,
                        "status": status_code,
                        "duration_ms": round(elapsed * 1000, 2),
                        "sampled": status_code < 500 and elapsed < 0.25,
                    }
                },
            )


@asynccontextmanager
async def _connection(request: Request) -> AsyncIterator[asyncpg.Connection]:
    pool: asyncpg.Pool = request.app.state.pool
    try:
        connection = await pool.acquire(timeout=settings.db_acquire_timeout_seconds)
    except (asyncio.TimeoutError, TimeoutError) as exc:
        DB_POOL_TIMEOUTS.inc()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database connection pool saturated",
        ) from exc
    try:
        yield connection
    finally:
        await pool.release(connection)


def _playlist_cache_key(playlist_id: UUID) -> str:
    return f"tinytune:playlist:{playlist_id}"


async def _invalidate_playlist(redis: Redis, playlist_id: UUID) -> None:
    try:
        await redis.delete(_playlist_cache_key(playlist_id))
        CACHE_OPERATIONS.labels("invalidate").inc()
    except RedisError:
        CACHE_OPERATIONS.labels("error").inc()
        logger.warning(
            "cache invalidation failed",
            extra={"fields": {"playlist_id": str(playlist_id)}},
            exc_info=True,
        )


async def _load_playlist(connection: asyncpg.Connection, playlist_id: UUID):
    playlist = await connection.fetchrow(
        "SELECT id, name, created_at, description, cover, owner_id FROM playlists WHERE id = $1", playlist_id
    )
    if playlist is None:
        return None
    tracks = await connection.fetch(
        """
        SELECT id, title, artist, position
        FROM tracks
        WHERE playlist_id = $1
        ORDER BY position
        """,
        playlist_id,
    )
    return {
        "id": str(playlist["id"]),
        "name": playlist["name"],
        "description": playlist["description"],
        "cover": playlist["cover"],
        "owner_id": str(playlist["owner_id"]) if playlist["owner_id"] else None,
        "created_at": playlist["created_at"].isoformat(),
        "tracks": [
            {
                "id": str(track["id"]),
                "title": track["title"],
                "artist": track["artist"],
                "position": track["position"],
            }
            for track in tracks
        ],
    }


async def _idempotent_event_id(redis: Redis, key: str | None) -> UUID:
    if not key:
        return uuid4()
    digest = hashlib.sha256(key.encode()).hexdigest()
    redis_key = f"tinytune:idempotency:{digest}"
    existing = await redis.get(redis_key)
    if existing:
        return UUID(existing)
    candidate = uuid4()
    if await redis.set(redis_key, str(candidate), ex=86400, nx=True):
        return candidate
    return UUID(await redis.get(redis_key))


@app.get("/health/live", include_in_schema=False)
async def liveness():
    return {"status": "alive"}


@app.get("/health/ready", include_in_schema=False)
async def readiness(request: Request):
    checks = {"postgres": False, "redis": False}
    try:
        async with _connection(request) as connection:
            checks["postgres"] = (await connection.fetchval("SELECT 1")) == 1
        checks["redis"] = bool(await request.app.state.redis.ping())
    except Exception:
        logger.warning("readiness check failed", exc_info=True)
    if not all(checks.values()):
        raise HTTPException(status_code=503, detail=checks)
    return {"status": "ready", "checks": checks}


@app.get("/metrics", include_in_schema=False)
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/api/v1/playlists", status_code=status.HTTP_201_CREATED)
async def create_playlist(payload: PlaylistCreate, request: Request):
    playlist_id = uuid4()
    user = await current_user(request)
    async with _connection(request) as connection:
        row = await connection.fetchrow(
            """
            INSERT INTO playlists(id, name, description, cover, owner_id)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, name, created_at
            """,
            playlist_id,
            payload.name,
            payload.description,
            payload.cover,
            UUID(user["id"]),
        )
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "created_at": row["created_at"].isoformat(),
        "tracks": [],
    }


@app.post(
    "/api/v1/playlists/{playlist_id}/tracks", status_code=status.HTTP_201_CREATED
)
async def add_track(playlist_id: UUID, payload: TrackCreate, request: Request):
    track_id = uuid4()
    user = await current_user(request)
    async with _connection(request) as connection:
        async with connection.transaction():
            await playlist_role(connection, playlist_id, UUID(user["id"]), edit=True, lock=True)
            position = await connection.fetchval(
                "SELECT COALESCE(MAX(position), 0) + 1 FROM tracks WHERE playlist_id = $1",
                playlist_id,
            )
            row = await connection.fetchrow(
                """
                INSERT INTO tracks(id, playlist_id, title, artist, position)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, title, artist, position
                """,
                track_id,
                playlist_id,
                payload.title,
                payload.artist,
                position,
            )
    await _invalidate_playlist(request.app.state.redis, playlist_id)
    return {
        "id": str(row["id"]),
        "title": row["title"],
        "artist": row["artist"],
        "position": row["position"],
    }


@app.get("/api/v1/playlists/{playlist_id}")
async def get_playlist(playlist_id: UUID, request: Request):
    user = await current_user(request)
    async with _connection(request) as connection:
        role = await playlist_role(connection, playlist_id, UUID(user["id"]))
    redis: Redis = request.app.state.redis
    cache_key = _playlist_cache_key(playlist_id)
    if settings.cache_enabled:
        try:
            cached = await redis.get(cache_key)
            if cached:
                CACHE_OPERATIONS.labels("hit").inc()
                return {**json.loads(cached), "role": role}
            CACHE_OPERATIONS.labels("miss").inc()
        except RedisError:
            CACHE_OPERATIONS.labels("error").inc()
            logger.warning("cache read failed", exc_info=True)

    async with _connection(request) as connection:
        playlist = await _load_playlist(connection, playlist_id)
    if playlist is None:
        raise HTTPException(status_code=404, detail="playlist not found")

    if settings.cache_enabled:
        try:
            await redis.set(cache_key, json.dumps(playlist), ex=settings.cache_ttl_seconds)
            CACHE_OPERATIONS.labels("write").inc()
        except RedisError:
            CACHE_OPERATIONS.labels("error").inc()
            logger.warning("cache write failed", exc_info=True)
    return {**playlist, "role": role}


@app.post(
    "/api/v1/playlists/{playlist_id}/plays", status_code=status.HTTP_202_ACCEPTED
)
async def record_play(
    playlist_id: UUID,
    payload: PlayCreate,
    request: Request,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    user = await current_user(request)
    async with _connection(request) as connection:
        await playlist_role(connection, playlist_id, UUID(user["id"]))
        valid_track = await connection.fetchval(
            "SELECT 1 FROM tracks WHERE id = $1 AND playlist_id = $2",
            payload.track_id,
            playlist_id,
        )
    if not valid_track:
        raise HTTPException(status_code=404, detail="track not found in playlist")

    redis: Redis = request.app.state.redis
    try:
        scoped_key = f"{user['id']}:{playlist_id}:{payload.track_id}:{idempotency_key}" if idempotency_key else None
        event_id = await _idempotent_event_id(redis, scoped_key)
    except RedisError as exc:
        if settings.play_mode == "async":
            raise HTTPException(status_code=503, detail="event stream unavailable") from exc
        event_id = uuid4()

    if settings.play_mode == "sync":
        async with _connection(request) as connection:
            async with connection.transaction():
                inserted = await connection.fetchval(
                    """
                    INSERT INTO processed_events(event_id)
                    VALUES ($1)
                    ON CONFLICT DO NOTHING
                    RETURNING event_id
                    """,
                    event_id,
                )
                if inserted:
                    await connection.execute(
                        """
                        INSERT INTO track_play_counts(track_id, play_count)
                        VALUES ($1, 1)
                        ON CONFLICT (track_id) DO UPDATE
                        SET play_count = track_play_counts.play_count + 1,
                            updated_at = NOW()
                        """,
                        payload.track_id,
                    )
                    PLAY_EVENTS_SYNC.labels("processed").inc()
                else:
                    PLAY_EVENTS_SYNC.labels("duplicate").inc()
        return {
            "event_id": str(event_id),
            "accepted": True,
            "processing": "synchronous",
            "duplicate": not bool(inserted),
        }

    try:
        await redis.xadd(
            settings.stream_name,
            {
                "event_id": str(event_id),
                "playlist_id": str(playlist_id),
                "track_id": str(payload.track_id),
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "request_id": request.state.request_id,
            },
        )
        PLAY_EVENTS_ENQUEUED.inc()
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="event stream unavailable") from exc
    return {
        "event_id": str(event_id),
        "accepted": True,
        "processing": "asynchronous",
    }


@app.get("/api/v1/playlists/{playlist_id}/stats")
async def playlist_stats(playlist_id: UUID, request: Request):
    user = await current_user(request)
    async with _connection(request) as connection:
        await playlist_role(connection, playlist_id, UUID(user["id"]))
        rows = await connection.fetch(
            """
            SELECT t.id, t.title, COALESCE(c.play_count, 0) AS play_count
            FROM tracks t
            LEFT JOIN track_play_counts c ON c.track_id = t.id
            WHERE t.playlist_id = $1
            ORDER BY t.position
            """,
            playlist_id,
        )
    return {
        "playlist_id": str(playlist_id),
        "consistency": "eventual" if settings.play_mode == "async" else "strong",
        "tracks": [
            {
                "track_id": str(row["id"]),
                "title": row["title"],
                "play_count": row["play_count"],
            }
            for row in rows
        ],
    }


@app.get("/api/v1/ops/status")
async def operations_status(request: Request):
    require_tools(request)
    redis: Redis = request.app.state.redis
    try:
        depth = await redis.xlen(settings.stream_name)
        pending = await redis.xpending(settings.stream_name, settings.consumer_group)
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="event stream unavailable") from exc
    return {
        "play_mode": settings.play_mode,
        "cache_enabled": settings.cache_enabled,
        "db_pool_size": settings.db_pool_size,
        "queue_depth": depth,
        "pending": pending.get("pending", 0) if isinstance(pending, dict) else pending,
    }


FRONTEND = Path(__file__).parent.parent / "frontend"
app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")


@app.get("/", include_in_schema=False)
@app.get("/console", include_in_schema=False)
async def frontend(request: Request):
    html = (FRONTEND / "index.html").read_text()
    surface = "tools" if request.headers.get("X-TinyTune-Surface") == "tools" else "customer"
    html = html.replace('name="tinytune-surface" content="customer"', f'name="tinytune-surface" content="{surface}"')
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.get("/docs", include_in_schema=False)
async def reference(request: Request):
    if request.headers.get("X-TinyTune-Surface") != "docs":
        raise HTTPException(404, "Not found")
    return get_swagger_ui_html(openapi_url="/openapi.json", title="TinyTune API reference",
                              swagger_ui_parameters={"supportedSubmitMethods": []},
                              swagger_favicon_url="/assets/favicon.svg",
                              swagger_js_url="/assets/vendor/swagger-ui-bundle.js",
                              swagger_css_url="/assets/vendor/swagger-ui.css")


@app.get("/openapi.json", include_in_schema=False)
async def schema(request: Request):
    if request.headers.get("X-TinyTune-Surface") != "docs":
        raise HTTPException(404, "Not found")
    return app.openapi()

