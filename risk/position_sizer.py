"""Position sizing: volatility (ATR) and fractional Kelly."""

from __future__ import annotations

import structlog

from config.settings import settings
from risk.models import OrderSide, PortfolioState

logger = structlog.get_logger(__name__)


class PositionSizer:
    """Compute order quantity from risk budget and market volatility."""

    def __init__(
        self,
        atr_multiplier_sl: float = 1.5,
        kelly_fraction: float = 0.25,
    ) -> None:
        self.atr_multiplier_sl = atr_multiplier_sl
        self.kelly_fraction = kelly_fraction

    def max_risk_usdt(self, portfolio: PortfolioState) -> float:
        return portfolio.total_equity_usdt * settings.max_position_risk_pct

    def size_from_atr(
        self,
        portfolio: PortfolioState,
        symbol: str,
        entry_price: float,
        atr: float,
        win_rate: float = 0.55,
        reward_risk: float = 2.0,
    ) -> float:
        """
        Risk-based size: risk_usdt / stop_distance.
        stop_distance = atr_multiplier * ATR
        """
        if entry_price <= 0 or atr <= 0:
            return 0.0

        risk_usdt = self.max_risk_usdt(portfolio)
        stop_distance = self.atr_multiplier_sl * atr
        if stop_distance <= 0:
            return 0.0

        qty = risk_usdt / stop_distance
        kelly_qty = self._fractional_kelly_qty(
            portfolio, entry_price, win_rate, reward_risk
        )
        if kelly_qty > 0:
            qty = min(qty, kelly_qty)

        max_notional = portfolio.total_equity_usdt * settings.max_single_asset_pct
        max_qty = max_notional / entry_price
        qty = min(qty, max_qty)

        reserve_cash = portfolio.total_equity_usdt * settings.usdt_reserve_pct
        available = max(0.0, portfolio.cash_usdt - reserve_cash)
        max_affordable = available / entry_price if entry_price > 0 else 0
        qty = min(qty, max_affordable)

        return max(0.0, qty)

    def _fractional_kelly_qty(
        self,
        portfolio: PortfolioState,
        price: float,
        win_rate: float,
        reward_risk: float,
    ) -> float:
        """Fractional Kelly: f* = (p*b - q) / b, use 25% of full Kelly."""
        p = max(0.0, min(1.0, win_rate))
        q = 1 - p
        b = max(reward_risk, 0.01)
        kelly = (p * b - q) / b
        if kelly <= 0:
            return 0.0
        fraction = kelly * self.kelly_fraction
        notional = portfolio.total_equity_usdt * fraction
        return notional / price

    def stop_loss_price(self, entry: float, atr: float, side: OrderSide) -> float:
        distance = self.atr_multiplier_sl * atr
        if side == OrderSide.BUY:
            return entry - distance
        return entry + distance

    def take_profit_price(
        self,
        entry: float,
        stop_loss: float,
        side: OrderSide,
        min_rr: float = 2.0,
    ) -> float:
        risk = abs(entry - stop_loss)
        reward = risk * min_rr
        if side == OrderSide.BUY:
            return entry + reward
        return entry - reward
