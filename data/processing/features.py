"""Technical indicator features via pandas-ta."""

from __future__ import annotations

import json

import pandas as pd
import structlog

from data.storage import timescale

logger = structlog.get_logger(__name__)

UPSERT_FEATURES_SQL = """
INSERT INTO features (time, symbol, timeframe, features)
VALUES ($1, $2, $3, $4::jsonb)
ON CONFLICT (time, symbol, timeframe) DO UPDATE SET
    features = EXCLUDED.features
"""


def calculate_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute indicators on a copy of OHLCV data. Index must be datetime."""
    if df.empty or len(df) < 30:
        return pd.DataFrame()

    import pandas_ta as ta

    result = df.copy()
    result.ta.rsi(length=14, append=True)
    result.ta.ema(length=9, append=True)
    result.ta.ema(length=21, append=True)
    result.ta.macd(append=True)
    result.ta.atr(length=14, append=True)
    result.ta.bbands(length=20, append=True)

    rename_map = {
        "RSI_14": "rsi_14",
        "EMA_9": "ema_9",
        "EMA_21": "ema_21",
        "ATRr_14": "atr_14",
    }
    result = result.rename(columns={k: v for k, v in rename_map.items() if k in result.columns})

    macd_cols = [c for c in result.columns if c.startswith("MACD")]
    for col in macd_cols:
        result = result.rename(columns={col: col.lower().replace("macd", "macd_")})

    bb_cols = [c for c in result.columns if c.startswith("BB")]
    for col in bb_cols:
        safe = col.lower().replace("%", "pct")
        result = result.rename(columns={col: safe})

    feature_cols = [
        c
        for c in result.columns
        if c not in ("open", "high", "low", "close", "volume", "num_trades")
    ]
    return result[feature_cols]


async def compute_and_store_features(
    symbol: str,
    timeframe: str,
    limit: int = 500,
) -> int:
    from data.storage.candles import fetch_candles_df

    df = await fetch_candles_df(symbol, timeframe, limit=limit)
    featured = calculate_features(df)
    if featured.empty:
        logger.warning("features_skipped", symbol=symbol, timeframe=timeframe, reason="insufficient_data")
        return 0

    pool = await timescale.get_pool()
    written = 0
    async with pool.acquire() as conn:
        for ts, row in featured.iterrows():
            if row.isna().any():
                continue
            payload = {k: (None if pd.isna(v) else float(v)) for k, v in row.items()}
            await conn.execute(
                UPSERT_FEATURES_SQL,
                ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                symbol.upper(),
                timeframe,
                json.dumps(payload),
            )
            written += 1

    logger.info("features_stored", symbol=symbol, timeframe=timeframe, rows=written)
    return written
