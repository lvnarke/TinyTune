from pathlib import Path

import asyncpg

from .config import settings


async def create_pool() -> asyncpg.Pool:
    pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=1,
        max_size=settings.db_pool_size,
        command_timeout=10,
    )
    schema = Path(__file__).resolve().parent.parent.joinpath("db", "init.sql").read_text()
    async with pool.acquire() as connection:
        await connection.execute(schema)
    return pool

