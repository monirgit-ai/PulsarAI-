#!/usr/bin/env python3
"""Generate live ensemble signal for a symbol."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from config.logging_config import configure_logging
from config.settings import settings
from data.processing.sentiment import aggregate_sentiment
from data.storage import timescale
from strategy.signal_generator import AISignalGenerator
from backtesting.data_loader import load_ohlcv_async


async def main_async(args: argparse.Namespace) -> int:
    ohlcv = await load_ohlcv_async(args.symbol, args.timeframe, limit=args.limit)
    if ohlcv.empty:
        print("No data in DB.", file=sys.stderr)
        return 1

    sentiment = await aggregate_sentiment(args.symbol)
    sentiment_score = float(sentiment.get("score", 0))

    gen = AISignalGenerator(args.symbol)
    gen.load_models()
    signal = await gen.generate(ohlcv, sentiment_score=sentiment_score)

    print(
        json.dumps(
            {
                "symbol": args.symbol,
                "action": signal.action.value,
                "size_pct": signal.size_pct,
                "metadata": signal.metadata,
                "sentiment": sentiment,
            },
            indent=2,
            default=str,
        )
    )
    await timescale.close_pool()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()
    configure_logging(settings.log_level)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
