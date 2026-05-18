"""Simple moving-average crossover strategy for backtest validation."""

from __future__ import annotations

import pandas as pd

from backtesting.models import Signal, SignalAction


class SimpleMovingAverageCrossover:
    """Fast/slow EMA crossover — baseline strategy for Phase 2 tests."""

    def __init__(
        self,
        symbol: str,
        fast_period: int = 9,
        slow_period: int = 21,
    ) -> None:
        self.symbol = symbol.upper()
        self.fast_period = fast_period
        self.slow_period = slow_period

    def on_bar(self, bar_index: int, history: pd.DataFrame) -> Signal | None:
        if bar_index < self.slow_period:
            return None

        closes = history["close"].iloc[: bar_index + 1]
        fast = closes.ewm(span=self.fast_period, adjust=False).mean()
        slow = closes.ewm(span=self.slow_period, adjust=False).mean()

        if len(fast) < 2:
            return None

        prev_fast, curr_fast = fast.iloc[-2], fast.iloc[-1]
        prev_slow, curr_slow = slow.iloc[-2], slow.iloc[-1]

        if prev_fast <= prev_slow and curr_fast > curr_slow:
            return Signal(SignalAction.BUY, self.symbol, size_pct=0.10)
        if prev_fast >= prev_slow and curr_fast < curr_slow:
            return Signal(SignalAction.SELL, self.symbol, size_pct=1.0)
        return None
