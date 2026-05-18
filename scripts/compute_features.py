#!/usr/bin/env python3
"""Compute technical features for symbols already in the database."""

from __future__ import annotations

import argparse
import asyncio

from config.logging_config import configure_logging
from config.settings import settings
from data.processing.features import compute_and_store_features
from data.storage import timescale


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default=settings.trading_symbols)
    parser.add_argument("--intervals", default=settings.historical_intervals)
    args = parser.parse_args()

    configure_logging(settings.log_level)
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    intervals = [i.strip() for i in args.intervals.split(",") if i.strip()]

    for symbol in symbols:
        for interval in intervals:
            n = await compute_and_store_features(symbol, interval)
            print(f"{symbol} {interval}: {n} feature rows")

    await timescale.close_pool()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
