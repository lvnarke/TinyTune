import asyncio
import hashlib
import logging
import os
import socket
import time
from uuid import UUID

from prometheus_client import start_http_server
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from .config import settings
from .db import create_pool
from .logging_config import configure_logging
from .metrics import WORKER_BATCH_SIZE, WORKER_DURATION, WORKER_EVENTS


configure_logging(settings.log_level)
logger = logging.getLogger("tinytune.worker")
MAX_RETRIES = 3
RETRY_HASH = "tinytune:play-event-retries"
DLQ_STREAM = "tinytune:play-events:dlq"


async def ensure_group(redis: Redis) -> None:
    try:
        await redis.xgroup_create(
            settings.stream_name, settings.consumer_group, id="0-0", mkstream=True
        )
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def process_event(pool, fields: dict[str, str]) -> bool:
    event_id = UUID(fields["event_id"])
    track_id = UUID(fields["track_id"])
    if settings.worker_processing_delay_ms:
        await asyncio.sleep(settings.worker_processing_delay_ms / 1000)
    async with pool.acquire(timeout=settings.db_acquire_timeout_seconds) as connection:
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
            if not inserted:
                return False
            await connection.execute(
                """
                INSERT INTO track_play_counts(track_id, play_count)
                VALUES ($1, 1)
                ON CONFLICT (track_id) DO UPDATE
                SET play_count = track_play_counts.play_count + 1,
                    updated_at = NOW()
                """,
                track_id,
            )
    return True


async def acknowledge(redis: Redis, message_id: str) -> None:
    await redis.xack(settings.stream_name, settings.consumer_group, message_id)
    await redis.xdel(settings.stream_name, message_id)
    await redis.hdel(RETRY_HASH, message_id)


async def handle_message(redis: Redis, pool, message_id: str, fields: dict[str, str]):
    started = time.perf_counter()
    try:
        processed = await process_event(pool, fields)
        await acknowledge(redis, message_id)
        result = "processed" if processed else "duplicate"
        WORKER_EVENTS.labels(result).inc()
        sample_bucket = int(hashlib.sha256(message_id.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
        if result == "duplicate" or sample_bucket < settings.success_log_sample_rate:
            logger.info(
                "event handled",
                extra={
                    "fields": {
                        "message_id": message_id,
                        "event_id": fields.get("event_id"),
                        "track_id": fields.get("track_id"),
                        "result": result,
                        "request_id": fields.get("request_id"),
                        "sampled": result == "processed",
                    }
                },
            )
    except Exception as exc:
        retries = await redis.hincrby(RETRY_HASH, message_id, 1)
        WORKER_EVENTS.labels("failed").inc()
        logger.error(
            "event processing failed",
            extra={
                "fields": {
                    "message_id": message_id,
                    "event_id": fields.get("event_id"),
                    "attempt": retries,
                }
            },
            exc_info=True,
        )
        if retries >= MAX_RETRIES:
            await redis.xadd(
                DLQ_STREAM,
                {
                    **fields,
                    "original_message_id": message_id,
                    "failure": str(exc)[:500],
                },
            )
            await acknowledge(redis, message_id)
            WORKER_EVENTS.labels("dead_lettered").inc()
            logger.error(
                "event moved to dead-letter stream",
                extra={"fields": {"message_id": message_id}},
            )
    finally:
        WORKER_DURATION.observe(time.perf_counter() - started)


async def claimed_messages(redis: Redis, consumer_name: str):
    response = await redis.xautoclaim(
        settings.stream_name,
        settings.consumer_group,
        consumer_name,
        min_idle_time=settings.worker_claim_idle_ms,
        start_id="0-0",
        count=settings.worker_batch_size,
    )
    return response[1] if response and len(response) > 1 else []


async def worker_loop() -> None:
    consumer_name = f"{socket.gethostname()}-{os.getpid()}"
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    pool = await create_pool()
    await ensure_group(redis)
    logger.info(
        "worker started",
        extra={
            "fields": {
                "consumer": consumer_name,
                "batch_size": settings.worker_batch_size,
                "processing_delay_ms": settings.worker_processing_delay_ms,
            }
        },
    )
    try:
        while True:
            messages = await claimed_messages(redis, consumer_name)
            if not messages:
                response = await redis.xreadgroup(
                    settings.consumer_group,
                    consumer_name,
                    {settings.stream_name: ">"},
                    count=settings.worker_batch_size,
                    block=1000,
                )
                messages = response[0][1] if response else []
            if not messages:
                continue
            WORKER_BATCH_SIZE.observe(len(messages))
            for message_id, fields in messages:
                await handle_message(redis, pool, message_id, fields)
    finally:
        await redis.aclose()
        await pool.close()


def main() -> None:
    start_http_server(9000)
    try:
        asyncio.run(worker_loop())
    except KeyboardInterrupt:
        logger.info("worker stopped")


if __name__ == "__main__":
    main()

