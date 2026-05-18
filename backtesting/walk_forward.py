"""Walk-forward validation — rolling train/test windows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd
import structlog

from backtesting.engine import BacktestEngine
from backtesting.metrics import GATE_MAX_DRAWDOWN_PCT, GATE_MIN_SHARPE, evaluate_gate
from backtesting.models import BacktestConfig, BacktestResult
from strategy.base import Strategy

logger = structlog.get_logger(__name__)

MIN_OUT_OF_SAMPLE_PERIODS = 10
MIN_BARS_PER_PERIOD = 500


@dataclass
class WalkForwardPeriod:
    period_index: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    result: BacktestResult


@dataclass
class WalkForwardReport:
    symbol: str
    timeframe: str
    periods: list[WalkForwardPeriod]
    aggregate_metrics: dict[str, float]
    passed: bool
    failure_reasons: list[str]


@dataclass
class WalkForwardConfig:
    train_months: int = 6
    test_months: int = 1
    min_periods: int = MIN_OUT_OF_SAMPLE_PERIODS
    min_bars_per_period: int = MIN_BARS_PER_PERIOD
    backtest_config: BacktestConfig | None = None


def _bars_per_month(timeframe: str) -> int:
    mapping = {
        "1m": 30 * 24 * 60,
        "5m": 30 * 24 * 12,
        "15m": 30 * 24 * 4,
        "1h": 30 * 24,
        "4h": 30 * 6,
        "1d": 30,
    }
    return mapping.get(timeframe, 30 * 24)


def split_walk_forward_periods(
    data: pd.DataFrame,
    timeframe: str,
    wf_config: WalkForwardConfig,
) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    """Return list of (train_df, test_df) slices."""
    bars_month = _bars_per_month(timeframe)
    train_bars = wf_config.train_months * bars_month
    test_bars = wf_config.test_months * bars_month
    min_test = wf_config.min_bars_per_period

    periods: list[tuple[pd.DataFrame, pd.DataFrame]] = []
    start = 0
    while start + train_bars + test_bars <= len(data):
        train_end = start + train_bars
        test_end = train_end + test_bars
        test_slice = data.iloc[train_end:test_end]
        if len(test_slice) >= min_test:
            periods.append((data.iloc[start:train_end], test_slice))
        start += test_bars

    return periods


def run_walk_forward(
    data: pd.DataFrame,
    strategy_factory: callable,
    symbol: str,
    timeframe: str = "1h",
    wf_config: WalkForwardConfig | None = None,
) -> WalkForwardReport:
    """
    Run out-of-sample backtests on rolling windows.
    `strategy_factory` is called per period: factory(symbol) -> Strategy.
    Train window is reserved for future parameter fitting (Phase 3+); for now
    we only evaluate on the test slice with a fixed strategy.
    """
    wf_config = wf_config or WalkForwardConfig()
    engine = BacktestEngine(wf_config.backtest_config)

    period_slices = split_walk_forward_periods(data, timeframe, wf_config)
    if len(period_slices) < wf_config.min_periods:
        return WalkForwardReport(
            symbol=symbol,
            timeframe=timeframe,
            periods=[],
            aggregate_metrics={},
            passed=False,
            failure_reasons=[
                f"Only {len(period_slices)} OOS periods; need {wf_config.min_periods}",
            ],
        )

    results: list[WalkForwardPeriod] = []
    for idx, (train_df, test_df) in enumerate(period_slices):
        strategy = strategy_factory(symbol)
        _ = train_df  # reserved for future optimization
        bt_result = engine.run(test_df, strategy, symbol, timeframe)
        results.append(
            WalkForwardPeriod(
                period_index=idx,
                train_start=train_df.index[0].to_pydatetime()
                if hasattr(train_df.index[0], "to_pydatetime")
                else train_df.index[0],
                train_end=train_df.index[-1].to_pydatetime()
                if hasattr(train_df.index[-1], "to_pydatetime")
                else train_df.index[-1],
                test_start=test_df.index[0].to_pydatetime()
                if hasattr(test_df.index[0], "to_pydatetime")
                else test_df.index[0],
                test_end=test_df.index[-1].to_pydatetime()
                if hasattr(test_df.index[-1], "to_pydatetime")
                else test_df.index[-1],
                result=bt_result,
            )
        )

    sharpes = [p.result.metrics.get("sharpe_ratio", 0.0) for p in results]
    drawdowns = [p.result.metrics.get("max_drawdown_pct", 100.0) for p in results]
    returns = [p.result.metrics.get("total_return_pct", 0.0) for p in results]
    pass_count = sum(1 for p in results if p.result.passed_gate)

    aggregate = {
        "periods": float(len(results)),
        "periods_passed_gate": float(pass_count),
        "mean_sharpe": round(sum(sharpes) / len(sharpes), 4),
        "mean_return_pct": round(sum(returns) / len(returns), 4),
        "worst_drawdown_pct": round(max(drawdowns), 4),
        "pct_periods_passed": round(pass_count / len(results) * 100, 2),
    }

    failure_reasons: list[str] = []
    if aggregate["mean_sharpe"] < GATE_MIN_SHARPE:
        failure_reasons.append(
            f"Mean OOS Sharpe {aggregate['mean_sharpe']:.2f} < {GATE_MIN_SHARPE}"
        )
    if aggregate["worst_drawdown_pct"] > GATE_MAX_DRAWDOWN_PCT:
        failure_reasons.append(
            f"Worst period drawdown {aggregate['worst_drawdown_pct']:.2f}% > {GATE_MAX_DRAWDOWN_PCT}%"
        )
    if pass_count < len(results) * 0.5:
        failure_reasons.append("Fewer than 50% of OOS periods passed individual gate")

    passed = len(failure_reasons) == 0
    logger.info("walk_forward_complete", symbol=symbol, passed=passed, aggregate=aggregate)

    return WalkForwardReport(
        symbol=symbol,
        timeframe=timeframe,
        periods=results,
        aggregate_metrics=aggregate,
        passed=passed,
        failure_reasons=failure_reasons,
    )
