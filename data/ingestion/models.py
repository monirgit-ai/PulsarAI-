"""Shared data models for ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Candle:
    time: datetime
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    num_trades: int | None = None

    @classmethod
    def from_rest_kline(cls, symbol: str, timeframe: str, row: list) -> Candle:
        """Parse Binance REST kline array."""
        return cls(
            time=datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc),
            symbol=symbol.upper(),
            timeframe=timeframe,
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
            num_trades=int(row[8]) if len(row) > 8 else None,
        )

    @classmethod
    def from_ws_kline(cls, kline: dict) -> Candle:
        """Parse Binance WebSocket kline payload (`k` object)."""
        return cls(
            time=datetime.fromtimestamp(kline["t"] / 1000, tz=timezone.utc),
            symbol=kline["s"].upper(),
            timeframe=kline["i"],
            open=float(kline["o"]),
            high=float(kline["h"]),
            low=float(kline["l"]),
            close=float(kline["c"]),
            volume=float(kline["v"]),
            num_trades=int(kline["n"]) if kline.get("n") is not None else None,
        )
