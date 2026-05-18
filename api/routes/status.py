"""Health and status endpoints."""

from fastapi import APIRouter

from config.settings import settings
from monitoring.health_check import run_health_check

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    status = await run_health_check()
    return {
        "status": "healthy" if status.healthy else "degraded",
        "environment": settings.environment,
        "paper_trading": settings.paper_trading,
        "checks": {
            "database": status.database,
            "redis": status.redis,
        },
        "details": status.details,
    }


@router.get("/status")
async def system_status() -> dict:
    return {
        "service": "PulsarAI",
        "version": "0.1.0",
        "phase": "1",
        "environment": settings.environment,
        "paper_trading": settings.paper_trading,
        "telegram_configured": settings.telegram_configured,
        "ports": {
            "api": settings.api_port,
            "postgres": settings.postgres_port,
            "redis": settings.redis_port,
            "grafana": settings.grafana_port,
        },
    }
