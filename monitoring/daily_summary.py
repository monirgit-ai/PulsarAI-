"""Daily P&L summary — sent at 00:00 UTC."""

from __future__ import annotations

from datetime import datetime, timezone

import structlog

from config.settings import settings
from data.storage import redis_cache
from monitoring.performance_tracker import PerformanceTracker
from monitoring.telegram_alerts import notify_daily_pnl_summary

logger = structlog.get_logger(__name__)

REDIS_LAST_SENT = "pulsarai:daily_summary:last_date"


class DailySummaryService:
    def __init__(self) -> None:
        self.tracker = PerformanceTracker()

    async def maybe_send(self) -> bool:
        """Send summary once per UTC day at configured hour."""
        now = datetime.now(timezone.utc)
        if now.hour != settings.daily_summary_hour_utc:
            return False

        today = now.strftime("%Y-%m-%d")
        redis = await redis_cache.get_redis()
        last = await redis.get(REDIS_LAST_SENT)
        last_str = last.decode() if isinstance(last, bytes) else (last or "")
        if last_str == today:
            return False

        snap = await self.tracker.collect()
        sent = await notify_daily_pnl_summary(
            equity_usdt=snap.equity_usdt,
            daily_pnl_usdt=snap.daily_pnl_usdt,
            realized_pnl_30d=snap.realized_pnl_30d,
            win_rate_30d=snap.win_rate_30d,
            sharpe_30d=snap.sharpe_30d,
            open_positions=snap.open_positions,
            fees_today=snap.fees_today_usdt,
            paper_trading=settings.paper_trading,
        )
        if sent:
            await redis.set(REDIS_LAST_SENT, today, ex=86400 * 2)
            logger.info("daily_summary_sent", date=today)
        return sent
