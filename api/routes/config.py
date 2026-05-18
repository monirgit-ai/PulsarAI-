"""Read-only config exposure (no secrets)."""

from fastapi import APIRouter

from config.settings import settings

router = APIRouter()


@router.get("/config")
async def get_public_config() -> dict:
    return {
        "environment": settings.environment,
        "paper_trading": settings.paper_trading,
        "initial_budget_usdt": settings.initial_budget_usdt,
        "risk_limits": {
            "max_position_risk_pct": settings.max_position_risk_pct,
            "max_open_positions": settings.max_open_positions,
            "max_single_asset_pct": settings.max_single_asset_pct,
            "max_daily_drawdown_pct": settings.max_daily_drawdown_pct,
            "min_trade_size_usdt": settings.min_trade_size_usdt,
            "usdt_reserve_pct": settings.usdt_reserve_pct,
        },
        "telegram_alerts_enabled": settings.telegram_alerts_enabled,
    }
