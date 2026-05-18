"""Redis cache client."""

from __future__ import annotations

import redis.asyncio as aioredis
import structlog

from config.settings import settings

logger = structlog.get_logger(__name__)

_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(settings.redis_url, decode_responses=True)
        logger.info("redis_client_created")
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
        logger.info("redis_client_closed")
