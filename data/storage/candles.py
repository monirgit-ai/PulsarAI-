"""Candle persistence and retrieval."""

from __future__ import annotations

import json
from datetime import datetime

import structlog

from data.ingestion.models import Candle
from data.storage import redis_cache, timescale

logger = structlog.get_logger(__name__)

UPSERT_CANDLE_SQL = """
INSERT INTO candles (
    time, symbol, timeframe, open, high, low, close, volume, num_trades
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
ON CONFLICT (time, symbol, timeframe) DO UPDATE SET
    open = EXCLUDED.open,
    high = EXCLUDED.high,
    low = EXCLUDED.low,
    close = EXCLUDED.close,
    volume = EXCLUDED.volume,
    num_trades = EXCLUDED.num_trades
"""


async def upsert_candle(candle: Candle) -> None:
    pool = await timescale.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            UPSERT_CANDLE_SQL,
            candle.time,
            candle.symbol,
            candle.timeframe,
            candle.open,
            candle.high,
            candle.low,
            candle.close,
            candle.volume,
            candle.num_trades,
        )


async def upsert_candles(candles: list[Candle]) -> int:
    if not candles:
        return 0
    pool = await timescale.get_pool()
    records = [
        (
            c.time,
            c.symbol,
            c.timeframe,
            c.open,
            c.high,
            c.low,
            c.close,
            c.volume,
            c.num_trades,
        )
        for c in candles
    ]
    async with pool.acquire() as conn:
        await conn.executemany(UPSERT_CANDLE_SQL, records)
    return len(candles)


async def cache_latest_candle(candle: Candle) -> None:
    redis = await redis_cache.get_redis()
    key = f"pulsarai:candle:{candle.symbol}:{candle.timeframe}:latest"
    payload = {
        "time": candle.time.isoformat(),
        "symbol": candle.symbol,
        "timeframe": candle.timeframe,
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
        "num_trades": candle.num_trades,
    }
    await redis.set(key, json.dumps(payload), ex=86400)
    await redis.set("pulsarai:ingestion:last_write", candle.time.isoformat(), ex=86400)


async def fetch_candles_df(symbol: str, timeframe: str, limit: int = 500):
    """Load recent candles as a pandas DataFrame (newest last)."""
    import pandas as pd

    pool = await timescale.get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT time, open, high, low, close, volume, num_trades
            FROM candles
            WHERE symbol = $1 AND timeframe = $2
            ORDER BY time ASC
            LIMIT $3
            """,
            symbol.upper(),
            timeframe,
            limit,
        )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([dict(r) for r in rows])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index("time")
    return df


async def count_candles(symbol: str | None = None) -> int:
    pool = await timescale.get_pool()
    async with pool.acquire() as conn:
        if symbol:
            return await conn.fetchval(
                "SELECT COUNT(*)::int FROM candles WHERE symbol = $1",
                symbol.upper(),
            )
        return await conn.fetchval("SELECT COUNT(*)::int FROM candles")
