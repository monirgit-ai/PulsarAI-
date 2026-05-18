"""Portfolio and trading performance metrics for Grafana and Telegram."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import structlog

from config.settings import settings
from data.storage import redis_cache, timescale
from monitoring import metrics as prom
from risk.circuit_breaker import CircuitBreaker
from services.portfolio_service import PortfolioService

logger = structlog.get_logger(__name__)


@dataclass
class PerformanceSnapshot:
    equity_usdt: float
    cash_usdt: float
    open_positions: int
    daily_pnl_usdt: float
    realized_pnl_30d: float
    win_rate_30d: float
    sharpe_30d: float
    max_drawdown_pct: float
    fees_today_usdt: float
    closed_trades_30d: int
    circuit_breaker_active: bool
    ws_connected: bool


class PerformanceTracker:
    def __init__(self) -> None:
        self.portfolio = PortfolioService()
        self.circuit = CircuitBreaker()

    async def collect(self) -> PerformanceSnapshot:
        portfolio = await self.portfolio.load_state()
        stats = await self._trade_stats()
        cb_active = await self.circuit.is_active()
        ws_connected = await self._ws_connected()

        snap = PerformanceSnapshot(
            equity_usdt=portfolio.total_equity_usdt,
            cash_usdt=portfolio.cash_usdt,
            open_positions=portfolio.open_position_count,
            daily_pnl_usdt=stats["daily_pnl"],
            realized_pnl_30d=stats["realized_pnl_30d"],
            win_rate_30d=stats["win_rate_30d"],
            sharpe_30d=stats["sharpe_30d"],
            max_drawdown_pct=stats["max_drawdown_pct"],
            fees_today_usdt=stats["fees_today"],
            closed_trades_30d=stats["closed_count_30d"],
            circuit_breaker_active=cb_active,
            ws_connected=ws_connected,
        )
        self._update_prometheus(snap)
        await self._cache_snapshot(snap)
        return snap

    async def _trade_stats(self) -> dict:
        pool = await timescale.get_pool()
        now = datetime.now(timezone.utc)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_ago = now - timedelta(days=30)

        async with pool.acquire() as conn:
            daily = await conn.fetchrow(
                """
                SELECT COALESCE(SUM(pnl_usdt), 0) AS pnl,
                       COALESCE(SUM(fees_paid), 0) AS fees
                FROM trades
                WHERE status = 'CLOSED' AND closed_at >= $1
                """,
                day_start,
            )
            rows = await conn.fetch(
                """
                SELECT pnl_usdt, pnl_pct, closed_at
                FROM trades
                WHERE status = 'CLOSED' AND closed_at >= $1
                ORDER BY closed_at
                """,
                month_ago,
            )
            candle_count = await conn.fetchval("SELECT COUNT(*) FROM candles")

        pnls = [float(r["pnl_usdt"] or 0) for r in rows]
        wins = sum(1 for p in pnls if p > 0)
        closed_count = len(pnls)
        win_rate = (wins / closed_count * 100) if closed_count else 0.0

        if len(pnls) > 1:
            mean = sum(pnls) / len(pnls)
            var = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
            std = math.sqrt(var) if var > 0 else 0.0
            sharpe = (mean / std) * math.sqrt(252) if std > 0 else 0.0
        else:
            sharpe = 0.0

        equity = settings.initial_budget_usdt
        peak = equity
        max_dd = 0.0
        for p in pnls:
            equity += p
            peak = max(peak, equity)
            dd = (peak - equity) / peak * 100 if peak > 0 else 0
            max_dd = max(max_dd, dd)

        prom.CANDLES_IN_DB.set(float(candle_count or 0))

        return {
            "daily_pnl": float(daily["pnl"] or 0),
            "fees_today": float(daily["fees"] or 0),
            "realized_pnl_30d": sum(pnls),
            "win_rate_30d": win_rate,
            "sharpe_30d": sharpe,
            "max_drawdown_pct": max_dd,
            "closed_count_30d": closed_count,
        }

    async def _ws_connected(self) -> bool:
        redis = await redis_cache.get_redis()
        status = await redis.get("pulsarai:ws:status")
        if status is None:
            return False
        val = status.decode() if isinstance(status, bytes) else str(status)
        return val == "connected"

    def _update_prometheus(self, snap: PerformanceSnapshot) -> None:
        prom.EQUITY_USDT.set(snap.equity_usdt)
        prom.CASH_USDT.set(snap.cash_usdt)
        prom.OPEN_POSITIONS.set(snap.open_positions)
        prom.DAILY_PNL_USDT.set(snap.daily_pnl_usdt)
        prom.WIN_RATE_30D.set(snap.win_rate_30d)
        prom.SHARPE_30D.set(snap.sharpe_30d)
        prom.MAX_DRAWDOWN_PCT.set(snap.max_drawdown_pct)
        prom.FEES_PAID_DAILY.set(snap.fees_today_usdt)
        prom.CIRCUIT_BREAKER_ACTIVE.set(1 if snap.circuit_breaker_active else 0)
        prom.WS_CONNECTED.set(1 if snap.ws_connected else 0)

    async def _cache_snapshot(self, snap: PerformanceSnapshot) -> None:
        redis = await redis_cache.get_redis()
        await redis.hset(
            "pulsarai:performance:latest",
            mapping={
                "equity_usdt": str(snap.equity_usdt),
                "daily_pnl_usdt": str(snap.daily_pnl_usdt),
                "open_positions": str(snap.open_positions),
                "win_rate_30d": str(snap.win_rate_30d),
                "sharpe_30d": str(snap.sharpe_30d),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
