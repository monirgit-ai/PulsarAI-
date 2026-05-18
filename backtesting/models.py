"""Backtesting domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SignalAction(str, Enum):
    HOLD = "HOLD"
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class Signal:
    action: SignalAction
    symbol: str
    size_pct: float = 1.0  # fraction of available capital for BUY; fraction of position for SELL
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Fill:
    time: datetime
    symbol: str
    side: str
    quantity: float
    price: float
    fee: float
    slippage_pct: float
    partial: bool = False


@dataclass
class TradeRecord:
    symbol: str
    side: str
    entry_time: datetime
    exit_time: datetime | None
    entry_price: float
    exit_price: float | None
    quantity: float
    pnl_usdt: float
    pnl_pct: float
    fees_paid: float
    bars_held: int


@dataclass
class BacktestConfig:
    initial_capital_usdt: float = 10_000.0
    taker_fee_pct: float = 0.00075
    maker_fee_pct: float = 0.0
    slippage_large_cap_pct: float = 0.0005
    slippage_alt_pct: float = 0.0015
    large_cap_symbols: frozenset[str] = frozenset({"BTCUSDT", "ETHUSDT", "BNBUSDT"})
    max_position_pct: float = 0.20
    partial_fill_max_volume_pct: float = 0.10
    min_trade_usdt: float = 50.0


@dataclass
class BacktestResult:
    config: BacktestConfig
    symbol: str
    timeframe: str
    start_time: datetime
    end_time: datetime
    initial_capital: float
    final_equity: float
    trades: list[TradeRecord]
    equity_curve: list[tuple[datetime, float]]
    metrics: dict[str, float]
    passed_gate: bool
    gate_reasons: list[str]
