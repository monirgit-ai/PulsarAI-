#!/usr/bin/env python3
"""Download historical OHLCV from Binance into TimescaleDB."""

from __future__ import annotations

import argparse
import asyncio
import sys

from config.logging_config import configure_logging
from config.settings import settings
from data.ingestion.binance_rest import download_history
from data.ingestion.universe import fetch_top_usdt_pairs, parse_symbol_list
from data.processing.features import compute_and_store_features
from data.storage import timescale


async def main() -> int:
    parser = argparse.ArgumentParser(description="Download Binance OHLCV history")
    parser.add_argument("--symbols", help="Comma-separated symbols (default: env TRADING_SYMBOLS)")
    parser.add_argument("--intervals", help="Comma-separated intervals (default: env)")
    parser.add_argument("--days", type=int, default=None, help="Days of history")
    parser.add_argument("--top", type=int, help="Use top N USDT pairs by volume")
    parser.add_argument("--features", action="store_true", help="Compute features after download")
    args = parser.parse_args()

    configure_logging(settings.log_level)

    symbols: list[str] | None = None
    if args.top:
        symbols = await fetch_top_usdt_pairs(args.top)
    elif args.symbols:
        symbols = parse_symbol_list(args.symbols)

    intervals = None
    if args.intervals:
        intervals = [x.strip() for x in args.intervals.split(",") if x.strip()]

    totals = await download_history(symbols=symbols, intervals=intervals, days=args.days)
    print("Download complete:")
    for key, count in totals.items():
        print(f"  {key}: {count} candles")

    if args.features:
        sym_list = symbols or settings.trading_symbol_list
        iv_list = intervals or settings.historical_interval_list
        for symbol in sym_list:
            for interval in iv_list:
                n = await compute_and_store_features(symbol, interval)
                print(f"  features {symbol} {interval}: {n} rows")

    await timescale.close_pool()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
