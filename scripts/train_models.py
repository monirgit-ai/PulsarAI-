#!/usr/bin/env python3
"""Train Phase 3 models: regime, TFT, RL for a symbol."""

from __future__ import annotations

import argparse
import asyncio
import sys

from config.logging_config import configure_logging
from config.settings import settings
from data.storage import timescale
from models.regime_classifier import RegimeClassifier, ModelValidationError
from models.rl_agent import RLTradingAgent
from models.tft_model import TFTDirectionModel
from backtesting.data_loader import load_ohlcv_async


async def _load_data(symbol: str, timeframe: str, limit: int) -> object:
    return await load_ohlcv_async(symbol, timeframe, limit=limit)


def main() -> int:
    parser = argparse.ArgumentParser(description="Train PulsarAI models")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--skip-regime", action="store_true")
    parser.add_argument("--skip-tft", action="store_true")
    parser.add_argument("--skip-rl", action="store_true")
    parser.add_argument("--rl-timesteps", type=int, default=30_000)
    parser.add_argument("--tft-epochs", type=int, default=25)
    args = parser.parse_args()

    configure_logging(settings.log_level)

    ohlcv = asyncio.run(_load_data(args.symbol, args.timeframe, args.limit))
    if ohlcv.empty or len(ohlcv) < 500:
        print("Need at least 500 candles. Run download_history first.", file=sys.stderr)
        return 1

    print(f"Training on {len(ohlcv)} bars for {args.symbol} {args.timeframe}")

    if not args.skip_regime:
        regime = RegimeClassifier(args.symbol)
        try:
            metrics = regime.train(ohlcv)
            path = regime.save()
            print(f"Regime: accuracy={metrics['oos_accuracy']:.2%} saved={path}")
        except ModelValidationError as exc:
            print(f"Regime FAILED gate: {exc}", file=sys.stderr)
            return 2

    if not args.skip_tft:
        tft = TFTDirectionModel(args.symbol)
        meta = tft.train(ohlcv, epochs=args.tft_epochs)
        path = tft.save()
        print(f"TFT: dir_acc={meta.get('directional_accuracy', 0):.2%} saved={path}")

    if not args.skip_rl:
        rl = RLTradingAgent(args.symbol)
        meta = rl.train(ohlcv, timesteps=args.rl_timesteps)
        path = rl.save()
        print(f"RL: timesteps={meta['timesteps']} saved={path}")

    asyncio.run(timescale.close_pool())
    print("Training complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
