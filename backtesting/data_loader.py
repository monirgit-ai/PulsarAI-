"""Load OHLCV data for backtests from TimescaleDB or parquet."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pandas as pd

from data.storage.candles import fetch_candles_df


async def load_ohlcv_async(symbol: str, timeframe: str, limit: int = 50_000) -> pd.DataFrame:
    df = await fetch_candles_df(symbol, timeframe, limit=limit)
    if df.empty:
        return df
    return df.rename(
        columns={
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
        }
    )


def load_ohlcv_from_parquet(path: str | Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    if "time" in df.columns:
        df = df.set_index("time")
    return df.sort_index()


def load_ohlcv(symbol: str, timeframe: str, limit: int = 50_000) -> pd.DataFrame:
    return asyncio.run(load_ohlcv_async(symbol, timeframe, limit))
