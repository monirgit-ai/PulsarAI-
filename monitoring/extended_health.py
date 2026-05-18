"""Extended health checks — DB latency, Redis, WebSocket, Binance API."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import structlog

from config.settings import settings
from data.storage import redis_cache, timescale
from monitoring import metrics as prom
from monitoring.health_check import check_database, check_redis

logger = structlog.get_logger(__name__)


@dataclass
class ExtendedHealthStatus:
    healthy: bool
    database: bool
    redis: bool
    websocket: bool
    binance_api: bool
    db_latency_ms: float
    details: dict[str, str] = field(default_factory=dict)


async def check_db_latency() -> tuple[bool, float, str]:
    try:
        start = time.perf_counter()
        pool = await timescale.get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        ms = (time.perf_counter() - start) * 1000
        prom.DB_LATENCY_MS.set(ms)
        ok = ms < 100.0
        detail = f"{ms:.1f}ms" + (" (slow)" if not ok else "")
        return ok, ms, detail
    except Exception as exc:
        logger.exception("db_latency_check_failed")
        prom.DB_LATENCY_MS.set(-1)
        return False, -1.0, str(exc)


async def check_websocket() -> tuple[bool, str]:
    if not settings.ingestion_enabled:
        return True, "ingestion_disabled"
    redis = await redis_cache.get_redis()
    status = await redis.get("pulsarai:ws:status")
    if status is None:
        prom.WS_CONNECTED.set(0)
        return False, "unknown"
    val = status.decode() if isinstance(status, bytes) else str(status)
    connected = val == "connected"
    prom.WS_CONNECTED.set(1 if connected else 0)
    return connected, val


async def check_binance_api() -> tuple[bool, str]:
    if not settings.binance_api_key:
        return True, "no_api_key_configured"
    try:
        from binance import AsyncClient

        client = await AsyncClient.create(
            settings.binance_api_key,
            settings.binance_api_secret,
            testnet=settings.binance_testnet,
        )
        try:
            await client.ping()
            return True, "ok"
        finally:
            await client.close_connection()
    except Exception as exc:
        logger.exception("binance_ping_failed")
        return False, str(exc)


async def run_extended_health_check() -> ExtendedHealthStatus:
    db_ok, db_detail = await check_database()
    redis_ok, redis_detail = await check_redis()
    db_lat_ok, db_ms, db_lat_detail = await check_db_latency()
    ws_ok, ws_detail = await check_websocket()
    binance_ok, binance_detail = await check_binance_api()

    prom.REDIS_CONNECTED.set(1 if redis_ok else 0)

    healthy = db_ok and redis_ok and db_lat_ok and ws_ok and binance_ok
    return ExtendedHealthStatus(
        healthy=healthy,
        database=db_ok,
        redis=redis_ok,
        websocket=ws_ok,
        binance_api=binance_ok,
        db_latency_ms=db_ms,
        details={
            "database": db_detail,
            "redis": redis_detail,
            "db_latency": db_lat_detail,
            "websocket": ws_detail,
            "binance_api": binance_detail,
        },
    )
