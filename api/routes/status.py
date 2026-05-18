"""Health and status endpoints."""

from fastapi import APIRouter

from config.settings import settings
from data.storage import redis_cache
from data.storage.candles import count_candles
from monitoring.health_check import run_health_check

router = APIRouter()


async def _ingestion_status() -> dict:
    redis = await redis_cache.get_redis()
    ws_status = await redis.get("pulsarai:ws:status")
    last_write = await redis.get("pulsarai:ingestion:last_write")
    return {
        "enabled": settings.ingestion_enabled,
        "websocket": ws_status or "unknown",
        "last_candle_write": last_write,
        "symbols": settings.trading_symbol_list,
        "ws_intervals": settings.ws_kline_interval_list,
    }


@router.get("/health")
async def health() -> dict:
    status = await run_health_check()
    ingestion = await _ingestion_status()
    return {
        "status": "healthy" if status.healthy else "degraded",
        "environment": settings.environment,
        "paper_trading": settings.paper_trading,
        "checks": {
            "database": status.database,
            "redis": status.redis,
        },
        "details": status.details,
        "ingestion": ingestion,
    }


@router.get("/status")
async def system_status() -> dict:
    candle_count = await count_candles()
    ingestion = await _ingestion_status()
    return {
        "service": "PulsarAI",
        "version": "0.1.0",
        "phase": "5-monitoring",
        "environment": settings.environment,
        "paper_trading": settings.paper_trading,
        "telegram_configured": settings.telegram_configured,
        "candles_in_db": candle_count,
        "ingestion": ingestion,
        "ports": {
            "api": settings.api_port,
            "postgres": settings.postgres_port,
            "redis": settings.redis_port,
            "grafana": settings.grafana_port,
        },
    }
