import numpy as np
import pandas as pd

from backtesting.engine import BacktestEngine
from backtesting.metrics import compute_metrics, evaluate_gate
from backtesting.models import BacktestConfig
from backtesting.walk_forward import WalkForwardConfig, run_walk_forward
from strategy.simple_ma import SimpleMovingAverageCrossover


def _synthetic_ohlcv(n: int = 800, trend: float = 0.0002) -> pd.DataFrame:
    idx = pd.date_range("2023-01-01", periods=n, freq="h", tz="UTC")
    rng = np.random.default_rng(0)
    close = 100 * np.exp(np.cumsum(rng.normal(trend, 0.002, n)))
    return pd.DataFrame(
        {
            "open": close * (1 + rng.normal(0, 0.001, n)),
            "high": close * 1.002,
            "low": close * 0.998,
            "close": close,
            "volume": rng.uniform(1000, 5000, n),
        },
        index=idx,
    )


def test_engine_runs_without_lookahead_crash() -> None:
    data = _synthetic_ohlcv(300)
    engine = BacktestEngine(BacktestConfig(initial_capital_usdt=10_000))
    result = engine.run(data, SimpleMovingAverageCrossover("TESTUSDT"), "TESTUSDT", "1h")
    assert result.final_equity > 0
    assert len(result.equity_curve) == len(data)
    assert "sharpe_ratio" in result.metrics


def test_metrics_and_gate() -> None:
    curve = [
        (pd.Timestamp("2024-01-01", tz="UTC"), 10_000.0),
        (pd.Timestamp("2024-06-01", tz="UTC"), 11_000.0),
    ]
    m = compute_metrics(curve, [], 10_000)
    assert m["total_return_pct"] == 10.0
    passed, _ = evaluate_gate({"sharpe_ratio": 1.5, "max_drawdown_pct": 5, "profit_factor": 1.2})
    assert passed


def test_walk_forward_minimum_periods() -> None:
    data = _synthetic_ohlcv(15_000)
    wf = WalkForwardConfig(
        train_months=1,
        test_months=1,
        min_periods=3,
        min_bars_per_period=100,
    )
    report = run_walk_forward(
        data,
        lambda sym: SimpleMovingAverageCrossover(sym),
        "TESTUSDT",
        "1h",
        wf,
    )
    assert len(report.periods) >= 3
    assert "mean_sharpe" in report.aggregate_metrics
