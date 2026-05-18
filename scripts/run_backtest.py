#!/usr/bin/env python3
"""Run event-driven backtest and optional walk-forward validation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backtesting.data_loader import load_ohlcv, load_ohlcv_from_parquet
from backtesting.engine import BacktestEngine
from backtesting.models import BacktestConfig
from backtesting.report_generator import generate_html_report, generate_walk_forward_html
from backtesting.walk_forward import WalkForwardConfig, run_walk_forward
from config.logging_config import configure_logging
from config.settings import settings
from strategy.simple_ma import SimpleMovingAverageCrossover


def main() -> int:
    parser = argparse.ArgumentParser(description="PulsarAI backtest runner")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--parquet", help="Load from parquet instead of DB")
    parser.add_argument("--capital", type=float, default=settings.initial_budget_usdt)
    parser.add_argument("--walk-forward", action="store_true")
    parser.add_argument("--output-dir", default="reports")
    args = parser.parse_args()

    configure_logging(settings.log_level)

    if args.parquet:
        data = load_ohlcv_from_parquet(args.parquet)
    else:
        data = load_ohlcv(args.symbol, args.timeframe)

    if data.empty or len(data) < 50:
        print("Not enough data. Download history first:", file=sys.stderr)
        print("  python scripts/download_history.py --days 90", file=sys.stderr)
        return 1

    config = BacktestConfig(initial_capital_usdt=args.capital)
    engine = BacktestEngine(config)
    strategy = SimpleMovingAverageCrossover(args.symbol)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.walk_forward:
        wf_config = WalkForwardConfig(backtest_config=config)
        report = run_walk_forward(
            data,
            lambda sym: SimpleMovingAverageCrossover(sym),
            args.symbol,
            args.timeframe,
            wf_config,
        )
        html_path = generate_walk_forward_html(
            report, out_dir / f"walkforward_{args.symbol}_{args.timeframe}.html"
        )
        print(json.dumps({"passed": report.passed, "aggregate": report.aggregate_metrics}, indent=2))
        print(f"Report: {html_path}")
        return 0 if report.passed else 2

    result = engine.run(data, strategy, args.symbol, args.timeframe)
    html_path = generate_html_report(result, out_dir / f"backtest_{args.symbol}_{args.timeframe}.html")

    print(json.dumps({"passed_gate": result.passed_gate, "metrics": result.metrics}, indent=2))
    print(f"Gate reasons: {result.gate_reasons or ['ok']}")
    print(f"Report: {html_path}")
    return 0 if result.passed_gate else 2


if __name__ == "__main__":
    raise SystemExit(main())
