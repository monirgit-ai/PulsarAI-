"""LightGBM market regime classifier."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import structlog
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

from models.common import REGIME_LABELS, artifact_path
from models.regime_labeling import (
    build_regime_features,
    label_regimes,
    regime_feature_columns,
)

logger = structlog.get_logger(__name__)

MIN_OOS_ACCURACY = 0.70


class ModelValidationError(Exception):
    pass


@dataclass
class RegimePrediction:
    regime: str
    confidence: float
    scores: dict[str, float]


class RegimeClassifier:
    def __init__(self, symbol: str = "BTCUSDT") -> None:
        self.symbol = symbol.upper()
        self.model: lgb.LGBMClassifier | None = None
        self.label_encoder = LabelEncoder()
        self.label_encoder.fit(list(REGIME_LABELS))
        self.feature_columns = regime_feature_columns()
        self.metadata: dict = {}

    def prepare_training_data(self, ohlcv: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
        featured = build_regime_features(ohlcv)
        labels = label_regimes(ohlcv)
        cols = [c for c in self.feature_columns if c in featured.columns]
        X = featured[cols].copy()
        mask = X.notna().all(axis=1) & labels.notna()
        return X[mask], labels[mask]

    def train(
        self,
        ohlcv: pd.DataFrame,
        *,
        test_size: float = 0.2,
        min_accuracy: float = MIN_OOS_ACCURACY,
    ) -> dict[str, float]:
        X, y = self.prepare_training_data(ohlcv)
        if len(X) < 200:
            raise ModelValidationError(f"Insufficient samples: {len(X)} < 200")

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, shuffle=False
        )
        y_train_enc = self.label_encoder.transform(y_train)
        y_test_enc = self.label_encoder.transform(y_test)

        self.model = lgb.LGBMClassifier(
            n_estimators=200,
            learning_rate=0.05,
            max_depth=6,
            num_leaves=31,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
        )
        self.model.fit(
            X_train,
            y_train_enc,
            eval_set=[(X_test, y_test_enc)],
            callbacks=[lgb.early_stopping(20, verbose=False)],
        )

        preds = self.label_encoder.inverse_transform(self.model.predict(X_test))
        accuracy = accuracy_score(y_test, preds)
        self.metadata = {
            "symbol": self.symbol,
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "samples": len(X),
            "oos_accuracy": round(float(accuracy), 4),
            "features": self.feature_columns,
        }

        if accuracy < min_accuracy:
            raise ModelValidationError(
                f"OOS accuracy {accuracy:.2%} below minimum {min_accuracy:.0%}"
            )

        logger.info("regime_model_trained", **self.metadata)
        return {"oos_accuracy": float(accuracy), "samples": float(len(X))}

    def predict(self, ohlcv: pd.DataFrame) -> RegimePrediction:
        if self.model is None:
            raise RuntimeError("Model not trained or loaded")

        featured = build_regime_features(ohlcv)
        row = featured.iloc[[-1]]
        cols = [c for c in self.feature_columns if c in row.columns]
        if row[cols].isna().any(axis=None):
            return RegimePrediction("ranging", 0.5, {l: 0.2 for l in REGIME_LABELS})

        X = row[cols]
        proba = self.model.predict_proba(X)[0]
        classes = self.label_encoder.inverse_transform(np.arange(len(proba)))
        idx = int(np.argmax(proba))
        scores = {str(c): float(p) for c, p in zip(classes, proba)}
        return RegimePrediction(
            regime=str(classes[idx]),
            confidence=float(proba[idx]),
            scores=scores,
        )

    def regime_score(self, prediction: RegimePrediction) -> float:
        """Map regime to directional score in [-1, 1]."""
        mapping = {
            "trending_up": 1.0,
            "trending_down": -1.0,
            "ranging": 0.0,
            "volatile": 0.0,
            "crash": -0.8,
        }
        return mapping.get(prediction.regime, 0.0) * prediction.confidence

    def save(self, path: Path | None = None) -> Path:
        if self.model is None:
            raise RuntimeError("No model to save")
        path = path or artifact_path("regime", self.symbol)
        path = path.with_suffix(".pkl")
        joblib.dump(
            {
                "model": self.model,
                "label_encoder": self.label_encoder,
                "feature_columns": self.feature_columns,
                "metadata": self.metadata,
            },
            path,
        )
        meta_path = path.with_suffix(".json")
        meta_path.write_text(json.dumps(self.metadata, indent=2), encoding="utf-8")
        logger.info("regime_model_saved", path=str(path))
        return path

    def load(self, path: Path) -> None:
        payload = joblib.load(path)
        self.model = payload["model"]
        self.label_encoder = payload["label_encoder"]
        self.feature_columns = payload["feature_columns"]
        self.metadata = payload.get("metadata", {})
        self.symbol = self.metadata.get("symbol", self.symbol)
        logger.info("regime_model_loaded", path=str(path))
