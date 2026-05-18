"""TimescaleDB connection pool and helpers."""

from __future__ import annotations

import asyncpg
import structlog

from config.settings import settings

logger = structlog.get_logger(__name__)

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            settings.asyncpg_dsn,
            min_size=1,
            max_size=10,
            command_timeout=60,
        )
        logger.info("timescale_pool_created")
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("timescale_pool_closed")
