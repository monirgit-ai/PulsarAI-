"""Heuristic regime labels from OHLCV features (training targets)."""

from __future__ import annotations

import pandas as pd

from models.common import REGIME_LABELS

LABEL_TO_SCORE = {
    "trending_up": 1.0,
    "trending_down": -1.0,
    "ranging": 0.0,
    "volatile": 0.0,
    "crash": -1.0,
}


def build_regime_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build features for regime classification from OHLCV."""
    import pandas_ta as ta

    out = df.copy()
    if "close" not in out.columns:
        raise ValueError("DataFrame must include close column")

    out.ta.adx(length=14, append=True)
    out.ta.atr(length=14, append=True)
    out.ta.bbands(length=20, append=True)

    out["return_24h"] = out["close"].pct_change(24)
    out["return_4h"] = out["close"].pct_change(4)
    out["volume_ratio"] = out["volume"] / out["volume"].rolling(24).mean()

    if "ATRr_14" in out.columns:
        out["atr_pct"] = out["ATRr_14"] / out["close"]
    else:
        out["atr_pct"] = out["close"].rolling(14).std() / out["close"]

    bbu = next((c for c in out.columns if str(c).startswith("BBU")), None)
    bbl = next((c for c in out.columns if str(c).startswith("BBL")), None)
    if bbu and bbl:
        out["bb_width"] = (out[bbu] - out[bbl]) / out["close"]
    else:
        out["bb_width"] = out["close"].rolling(20).std() / out["close"]

    out = out.rename(
        columns={
            "ADX_14": "adx_14",
            "ATRr_14": "atr_14",
        }
    )
    return out


def label_regimes(df: pd.DataFrame) -> pd.Series:
    """
    Rule-based labels for supervised training.
    Uses only past/current bar data (no future leak in features used for labeling at train time
    — labels here use same-bar returns which is acceptable for historical labeling only).
    """
    featured = build_regime_features(df)
    labels = pd.Series(index=df.index, dtype="object")

    for i in range(len(featured)):
        row = featured.iloc[i]
        ret24 = row.get("return_24h", 0) or 0
        atr_pct = row.get("atr_pct", 0) or 0
        adx = row.get("adx_14", 0) or 0
        bb_width = row.get("bb_width", 0) or 0

        if pd.isna(ret24):
            labels.iloc[i] = "ranging"
            continue

        if ret24 <= -0.08:
            labels.iloc[i] = "crash"
        elif atr_pct > 0.04 or bb_width > 0.06:
            labels.iloc[i] = "volatile"
        elif adx > 25 and ret24 > 0.01:
            labels.iloc[i] = "trending_up"
        elif adx > 25 and ret24 < -0.01:
            labels.iloc[i] = "trending_down"
        else:
            labels.iloc[i] = "ranging"

    return labels


def regime_feature_columns() -> list[str]:
    return ["adx_14", "atr_pct", "bb_width", "return_24h", "return_4h", "volume_ratio"]
