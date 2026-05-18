"""Strategy protocol for backtesting and live trading."""

from __future__ import annotations

from typing import Protocol

import pandas as pd

from backtesting.models import Signal


class Strategy(Protocol):
    """Strategy receives only historical bars up to the current index (no look-ahead)."""

    def on_bar(self, bar_index: int, history: pd.DataFrame) -> Signal | None:
        """
        Called after bar `bar_index` closes.
        `history` contains rows 0..bar_index inclusive.
        Return a Signal to act on the next bar open, or None / HOLD.
        """
        ...
