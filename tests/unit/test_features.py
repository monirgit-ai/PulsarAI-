import numpy as np
import pandas as pd

from data.processing.features import calculate_features


def test_calculate_features_returns_indicators() -> None:
    n = 100
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    rng = np.random.default_rng(42)
    close = 100 + rng.standard_normal(n).cumsum()
    df = pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": rng.uniform(10, 100, n),
        },
        index=idx,
    )
    featured = calculate_features(df)
    assert not featured.empty
    assert "rsi_14" in featured.columns
    assert featured.iloc[-1].notna().any()
