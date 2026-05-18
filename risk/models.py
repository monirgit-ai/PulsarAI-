"""Risk and portfolio domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class OpenPosition:
    symbol: str
    side: str
    quantity: float
    entry_price: float
    notional_usdt: float
    opened_at: datetime

    @property
    def exposure_pct(self) -> float:
        return 0.0  # set by portfolio context


@dataclass
class PortfolioState:
    """Snapshot of account state for risk checks."""

    total_equity_usdt: float
    cash_usdt: float
    initial_equity_usdt: float
    daily_start_equity_usdt: float
    weekly_start_equity_usdt: float
    open_positions: dict[str, OpenPosition] = field(default_factory=dict)
    price_by_symbol: dict[str, float] = field(default_factory=dict)

    @property
    def open_position_count(self) -> int:
        return len(self.open_positions)

    @property
    def daily_drawdown_pct(self) -> float:
        if self.daily_start_equity_usdt <= 0:
            return 0.0
        return max(0.0, (self.daily_start_equity_usdt - self.total_equity_usdt) / self.daily_start_equity_usdt)

    @property
    def weekly_drawdown_pct(self) -> float:
        if self.weekly_start_equity_usdt <= 0:
            return 0.0
        return max(0.0, (self.weekly_start_equity_usdt - self.total_equity_usdt) / self.weekly_start_equity_usdt)

    def symbol_exposure_usdt(self, symbol: str) -> float:
        pos = self.open_positions.get(symbol.upper())
        if not pos:
            return 0.0
        price = self.price_by_symbol.get(symbol.upper(), pos.entry_price)
        return pos.quantity * price

    def symbol_exposure_pct(self, symbol: str) -> float:
        if self.total_equity_usdt <= 0:
            return 0.0
        return self.symbol_exposure_usdt(symbol) / self.total_equity_usdt


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: OrderSide
    quantity: float
    price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    signal_metadata: dict = field(default_factory=dict)

    @property
    def notional_usdt(self) -> float:
        if self.price is None:
            return 0.0
        return self.quantity * self.price
