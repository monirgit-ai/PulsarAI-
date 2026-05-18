"""Circuit breaker — halts trading on drawdown limits (persisted in Redis)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import structlog

from config.settings import settings
from data.storage import redis_cache

logger = structlog.get_logger(__name__)

REDIS_KEY_ACTIVE = "pulsarai:circuit_breaker:active"
REDIS_KEY_REASON = "pulsarai:circuit_breaker:reason"
REDIS_KEY_TRIGGERED_AT = "pulsarai:circuit_breaker:triggered_at"
REDIS_KEY_DAILY_START = "pulsarai:portfolio:daily_start_equity"
REDIS_KEY_WEEKLY_START = "pulsarai:portfolio:weekly_start_equity"


class CircuitBreaker:
    async def is_active(self) -> bool:
        redis = await redis_cache.get_redis()
        val = await redis.get(REDIS_KEY_ACTIVE)
        return val == "1" or val == b"1"

    async def get_reason(self) -> str | None:
        redis = await redis_cache.get_redis()
        raw = await redis.get(REDIS_KEY_REASON)
        if raw is None:
            return None
        return raw.decode() if isinstance(raw, bytes) else str(raw)

    async def trigger(self, reason: str) -> None:
        redis = await redis_cache.get_redis()
        await redis.set(REDIS_KEY_ACTIVE, "1")
        await redis.set(REDIS_KEY_REASON, reason)
        await redis.set(REDIS_KEY_TRIGGERED_AT, datetime.now(timezone.utc).isoformat())
        logger.warning("circuit_breaker_triggered", reason=reason)

        from monitoring.telegram_bot import send_alert

        await send_alert(
            f"Circuit breaker ACTIVE.\n{reason}",
            severity="CRITICAL",
            module="circuit_breaker",
            action="Trading halted. Manual review required before reset.",
        )

    async def reset(self) -> None:
        redis = await redis_cache.get_redis()
        await redis.delete(REDIS_KEY_ACTIVE, REDIS_KEY_REASON, REDIS_KEY_TRIGGERED_AT)
        logger.info("circuit_breaker_reset")

    async def record_equity_baselines(self, equity: float) -> None:
        redis = await redis_cache.get_redis()
        if not await redis.exists(REDIS_KEY_DAILY_START):
            await redis.set(REDIS_KEY_DAILY_START, str(equity))
        if not await redis.exists(REDIS_KEY_WEEKLY_START):
            await redis.set(REDIS_KEY_WEEKLY_START, str(equity))

    async def load_daily_start_equity(self, fallback: float) -> float:
        redis = await redis_cache.get_redis()
        raw = await redis.get(REDIS_KEY_DAILY_START)
        if raw is None:
            await redis.set(REDIS_KEY_DAILY_START, str(fallback))
            return fallback
        return float(raw.decode() if isinstance(raw, bytes) else raw)

    async def load_weekly_start_equity(self, fallback: float) -> float:
        redis = await redis_cache.get_redis()
        raw = await redis.get(REDIS_KEY_WEEKLY_START)
        if raw is None:
            await redis.set(REDIS_KEY_WEEKLY_START, str(fallback))
            return fallback
        return float(raw.decode() if isinstance(raw, bytes) else raw)

    async def check_drawdown_limits(self, portfolio_equity: float) -> str | None:
        daily_start = await self.load_daily_start_equity(portfolio_equity)
        weekly_start = await self.load_weekly_start_equity(portfolio_equity)

        daily_dd = (daily_start - portfolio_equity) / daily_start if daily_start > 0 else 0
        weekly_dd = (weekly_start - portfolio_equity) / weekly_start if weekly_start > 0 else 0

        if daily_dd >= settings.max_daily_drawdown_pct:
            return f"Daily drawdown {daily_dd:.2%} >= limit {settings.max_daily_drawdown_pct:.0%}"
        if weekly_dd >= settings.max_weekly_drawdown_pct:
            return f"Weekly drawdown {weekly_dd:.2%} >= limit {settings.max_weekly_drawdown_pct:.0%}"
        return None
