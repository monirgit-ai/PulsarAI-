#!/usr/bin/env python3
"""Paper trade one cycle: signal → risk → execute (PAPER_TRADING=true)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from backtesting.data_loader import load_ohlcv_async
from config.logging_config import configure_logging
from config.settings import settings
from data.processing.features import calculate_features
from data.processing.sentiment import aggregate_sentiment
from data.storage import timescale
from execution.order_manager import OrderManager
from services.portfolio_service import PortfolioService
from strategy.signal_generator import AISignalGenerator


async def main_async(args: argparse.Namespace) -> int:
    if not settings.paper_trading:
        print("PAPER_TRADING must be true for this script.", file=sys.stderr)
        return 2

    ohlcv = await load_ohlcv_async(args.symbol, args.timeframe, limit=args.limit)
    if ohlcv.empty:
        print("No OHLCV data.", file=sys.stderr)
        return 1

    features = calculate_features(ohlcv.copy())
    atr = PortfolioService.latest_atr(features)
    price = float(ohlcv["close"].iloc[-1])

    sentiment = await aggregate_sentiment(args.symbol)
    gen = AISignalGenerator(args.symbol)
    gen.load_models()
    signal = await gen.generate(features, sentiment_score=float(sentiment.get("score", 0)))

    portfolio_svc = PortfolioService()
    portfolio = await portfolio_svc.load_state(price_by_symbol={args.symbol.upper(): price})

    manager = OrderManager()
    order = await manager.process_signal(signal, portfolio, price, atr=atr)

    result = {
        "symbol": args.symbol,
        "signal": signal.action.value,
        "market_price": price,
        "atr": atr,
        "order_status": order.status.value if order else None,
        "filled_qty": order.filled_quantity if order else 0,
        "entry_price": order.entry_price if order else None,
    }
    print(json.dumps(result, indent=2, default=str))

    await timescale.close_pool()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one paper trading cycle")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()
    configure_logging(settings.log_level)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
