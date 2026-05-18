"""Build portfolio snapshots for risk checks and execution."""

from __future__ import annotations

from datetime import datetime, timezone

from config.settings import settings
from execution.trade_repository import TradeRepository
from risk.circuit_breaker import CircuitBreaker
from risk.models import OpenPosition, PortfolioState


class PortfolioService:
    def __init__(
        self,
        trade_repo: TradeRepository | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self.trades = trade_repo or TradeRepository()
        self.circuit = circuit_breaker or CircuitBreaker()

    async def load_state(
        self,
        *,
        cash_usdt: float | None = None,
        price_by_symbol: dict[str, float] | None = None,
    ) -> PortfolioState:
        cash = cash_usdt if cash_usdt is not None else settings.initial_budget_usdt
        open_rows = await self.trades.list_open_trades()
        positions: dict[str, OpenPosition] = {}
        prices = dict(price_by_symbol or {})

        for row in open_rows:
            symbol = row["symbol"].upper()
            entry = float(row["entry_price"])
            qty = float(row["quantity"])
            price = prices.get(symbol, entry)
            positions[symbol] = OpenPosition(
                symbol=symbol,
                side=row["side"],
                quantity=qty,
                entry_price=entry,
                notional_usdt=qty * price,
                opened_at=row["opened_at"],
            )
            prices.setdefault(symbol, entry)

        equity = cash + sum(p.notional_usdt for p in positions.values())
        daily_start = await self.circuit.load_daily_start_equity(equity)
        weekly_start = await self.circuit.load_weekly_start_equity(equity)
        await self.circuit.record_equity_baselines(equity)

        return PortfolioState(
            total_equity_usdt=equity,
            cash_usdt=cash,
            initial_equity_usdt=settings.initial_budget_usdt,
            daily_start_equity_usdt=daily_start,
            weekly_start_equity_usdt=weekly_start,
            open_positions=positions,
            price_by_symbol=prices,
        )

    @staticmethod
    def latest_atr(ohlcv_df, default: float = 100.0) -> float:
        if ohlcv_df is None or ohlcv_df.empty:
            return default
        if "atr_14" in ohlcv_df.columns:
            val = float(ohlcv_df["atr_14"].iloc[-1])
            return val if val > 0 else default
        return default
