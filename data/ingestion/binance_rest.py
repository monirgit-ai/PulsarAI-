"""Binance REST API — historical OHLCV download."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from binance import AsyncClient

from config.settings import settings
from data.ingestion.models import Candle
from data.ingestion.universe import _create_client, parse_symbol_list
from data.storage import candles as candle_store

logger = structlog.get_logger(__name__)

INTERVAL_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


async def fetch_klines_range(
    client: AsyncClient,
    symbol: str,
    interval: str,
    start: datetime,
    end: datetime,
) -> list[Candle]:
    """Fetch all klines between start and end (UTC)."""
    if interval not in INTERVAL_MS:
        raise ValueError(f"Unsupported interval: {interval}")

    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    result: list[Candle] = []

    while start_ms < end_ms:
        batch = await client.get_klines(
            symbol=symbol.upper(),
            interval=interval,
            startTime=start_ms,
            endTime=end_ms,
            limit=1000,
        )
        if not batch:
            break

        for row in batch:
            candle = Candle.from_rest_kline(symbol, interval, row)
            if candle.time.timestamp() * 1000 < end_ms:
                result.append(candle)

        last_open_ms = batch[-1][0]
        next_ms = last_open_ms + INTERVAL_MS[interval]
        if next_ms <= start_ms:
            break
        start_ms = next_ms
        await asyncio.sleep(settings.binance_rest_delay_seconds)

    return result


async def download_symbol_interval(
    symbol: str,
    interval: str,
    days: int,
    *,
    client: AsyncClient | None = None,
) -> int:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    own_client = client is None
    if own_client:
        client = await _create_client()

    try:
        logger.info(
            "download_start",
            symbol=symbol,
            interval=interval,
            days=days,
            start=start.isoformat(),
        )
        klines = await fetch_klines_range(client, symbol, interval, start, end)
        written = await candle_store.upsert_candles(klines)
        logger.info("download_complete", symbol=symbol, interval=interval, rows=written)
        return written
    finally:
        if own_client and client is not None:
            await client.close_connection()


async def download_history(
    symbols: list[str] | None = None,
    intervals: list[str] | None = None,
    days: int | None = None,
) -> dict[str, int]:
    symbols = symbols or parse_symbol_list(settings.trading_symbols) or ["BTCUSDT"]
    intervals = intervals or settings.historical_interval_list
    days = days or settings.historical_days

    totals: dict[str, int] = {}
    client = await _create_client()
    try:
        for symbol in symbols:
            for interval in intervals:
                key = f"{symbol}:{interval}"
                totals[key] = await download_symbol_interval(
                    symbol, interval, days, client=client
                )
    finally:
        await client.close_connection()

    return totals
