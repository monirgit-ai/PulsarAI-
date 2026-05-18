import numpy as np
import pandas as pd

from models.ensemble import EnsembleAggregator
from models.regime_labeling import label_regimes, build_regime_features
from models.regime_classifier import RegimeClassifier


def _ohlcv(n: int = 600) -> pd.DataFrame:
    idx = pd.date_range("2023-01-01", periods=n, freq="h", tz="UTC")
    rng = np.random.default_rng(42)
    close = 100 + np.cumsum(rng.normal(0.05, 1, n))
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": rng.uniform(1000, 5000, n),
        },
        index=idx,
    )


def test_regime_labeling() -> None:
    labels = label_regimes(_ohlcv(300))
    assert labels.isin(
        ["trending_up", "trending_down", "ranging", "volatile", "crash"]
    ).all()


def test_regime_train_predict() -> None:
    clf = RegimeClassifier("TESTUSDT")
    data = _ohlcv(800)
    metrics = clf.train(data, min_accuracy=0.0)
    assert metrics["samples"] > 200
    pred = clf.predict(data)
    assert pred.regime in ["trending_up", "trending_down", "ranging", "volatile", "crash"]
    assert 0 <= pred.confidence <= 1


def test_ensemble_aggregate() -> None:
    agg = EnsembleAggregator()
    result = agg.aggregate(0.8, 0.5, 0.3, 0.1)
    assert -1 <= result.final_score <= 1
    assert result.action.value in ("BUY", "SELL", "HOLD")
