"""Health checks for DB, Redis, and external services."""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg
import redis.asyncio as aioredis
import structlog

from config.settings import settings

logger = structlog.get_logger(__name__)


@dataclass
class HealthStatus:
    healthy: bool
    database: bool
    redis: bool
    details: dict[str, str]


async def check_database() -> tuple[bool, str]:
    try:
        conn = await asyncpg.connect(settings.asyncpg_dsn, timeout=5)
        try:
            await conn.fetchval("SELECT 1")
            return True, "ok"
        finally:
            await conn.close()
    except Exception as exc:
        logger.exception("health_db_failed")
        return False, str(exc)


async def check_redis() -> tuple[bool, str]:
    try:
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            pong = await client.ping()
            return bool(pong), "ok" if pong else "no pong"
        finally:
            await client.aclose()
    except Exception as exc:
        logger.exception("health_redis_failed")
        return False, str(exc)


async def run_health_check() -> HealthStatus:
    db_ok, db_detail = await check_database()
    redis_ok, redis_detail = await check_redis()
    healthy = db_ok and redis_ok
    return HealthStatus(
        healthy=healthy,
        database=db_ok,
        redis=redis_ok,
        details={"database": db_detail, "redis": redis_detail},
    )
