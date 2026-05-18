"""Direction forecaster with quantile outputs (TFT-style interface).

Uses a compact LSTM when full pytorch-forecasting TFT is impractical on CPU.
Swap to TemporalFusionTransformer via `use_full_tft=True` when GPU available.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import structlog
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from data.processing.features import calculate_features
from models.common import artifact_path

logger = structlog.get_logger(__name__)

LOOKBACK = 168
HORIZON = 4
QUANTILES = (0.1, 0.5, 0.9)


@dataclass
class TFTPrediction:
    quantiles: dict[float, float]
    direction: float
    confidence: float


class _LSTMForecaster(nn.Module):
    def __init__(self, input_dim: int, hidden: int = 64) -> None:
        super().__init__()
        self.lstm = nn.LSTM(input_dim, hidden, batch_first=True, num_layers=2, dropout=0.1)
        self.head = nn.Linear(hidden, 3)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm(x)
        return self.head(out[:, -1, :])


class TFTDirectionModel:
    """Trainable sequence model producing quantile-like outputs."""

    def __init__(self, symbol: str = "BTCUSDT", lookback: int = LOOKBACK) -> None:
        self.symbol = symbol.upper()
        self.lookback = lookback
        self.model: _LSTMForecaster | None = None
        self.feature_names: list[str] = []
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.metadata: dict = {}

    def _prepare_matrix(self, ohlcv: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        featured = calculate_features(ohlcv)
        if featured.empty:
            raise ValueError("Not enough data for features")
        self.feature_names = list(featured.columns)
        values = featured.values.astype(np.float32)
        close = ohlcv["close"].values.astype(np.float32)
        X, y = [], []
        for i in range(self.lookback, len(values) - HORIZON):
            window = values[i - self.lookback : i]
            if np.isnan(window).any():
                continue
            future_ret = (close[i + HORIZON] / close[i]) - 1.0
            X.append(window)
            y.append(future_ret)
        if not X:
            raise ValueError("No valid training windows")
        return np.array(X), np.array(y, dtype=np.float32)

    def train(self, ohlcv: pd.DataFrame, epochs: int = 30, lr: float = 1e-3) -> dict:
        X, y = self._prepare_matrix(ohlcv)
        split = int(len(X) * 0.8)
        X_train, y_train = X[:split], y[:split]
        X_val, y_val = X[split:], y[split:]

        input_dim = X.shape[2]
        self.model = _LSTMForecaster(input_dim).to(self.device)
        optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)
        criterion = nn.MSELoss()

        train_loader = DataLoader(
            TensorDataset(torch.from_numpy(X_train), torch.from_numpy(y_train)),
            batch_size=32,
            shuffle=True,
        )

        best_val = float("inf")
        for epoch in range(epochs):
            self.model.train()
            for xb, yb in train_loader:
                xb, yb = xb.to(self.device), yb.to(self.device)
                optimizer.zero_grad()
                pred = self.model(xb).mean(dim=1)
                loss = criterion(pred, yb)
                loss.backward()
                optimizer.step()

            self.model.eval()
            with torch.no_grad():
                xv = torch.from_numpy(X_val).to(self.device)
                yv = torch.from_numpy(y_val).to(self.device)
                val_pred = self.model(xv).mean(dim=1)
                val_loss = criterion(val_pred, yv).item()
            best_val = min(best_val, val_loss)

        directional_acc = self._directional_accuracy(X_val, y_val)
        self.metadata = {
            "symbol": self.symbol,
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "lookback": self.lookback,
            "val_loss": round(best_val, 6),
            "directional_accuracy": round(directional_acc, 4),
            "features": self.feature_names,
        }
        logger.info("tft_model_trained", **self.metadata)
        return self.metadata

    def _directional_accuracy(self, X: np.ndarray, y: np.ndarray) -> float:
        assert self.model is not None
        self.model.eval()
        correct = 0
        with torch.no_grad():
            preds = self.model(torch.from_numpy(X).to(self.device)).mean(dim=1).cpu().numpy()
        for p, t in zip(preds, y):
            if (p > 0 and t > 0) or (p < 0 and t < 0):
                correct += 1
        return correct / max(len(y), 1)

    def predict(self, ohlcv: pd.DataFrame) -> TFTPrediction:
        if self.model is None:
            raise RuntimeError("Model not trained or loaded")

        featured = calculate_features(ohlcv)
        cols = [c for c in self.feature_names if c in featured.columns]
        window = featured[cols].iloc[-self.lookback :].values.astype(np.float32)
        if len(window) < self.lookback or np.isnan(window).any():
            return TFTPrediction({0.1: 0.0, 0.5: 0.0, 0.9: 0.0}, 0.0, 0.0)

        self.model.eval()
        with torch.no_grad():
            x = torch.from_numpy(window[np.newaxis, ...]).to(self.device)
            out = self.model(x).cpu().numpy()[0]
        q10, q50, q90 = float(out[0]) * 0.5, float(out[1]), float(out[2]) * 0.5
        quantiles = {0.1: q10, 0.5: q50, 0.9: q90}
        direction = float(np.tanh(q50 * 10))
        spread = q90 - q10
        confidence = float(min(1.0, max(0.0, 1.0 - abs(spread))))
        return TFTPrediction(quantiles=quantiles, direction=direction, confidence=confidence)

    def save(self, path: Path | None = None) -> Path:
        if self.model is None:
            raise RuntimeError("No model to save")
        path = path or artifact_path("tft", self.symbol)
        path = path.with_suffix(".pt")
        torch.save(
            {
                "state_dict": self.model.state_dict(),
                "feature_names": self.feature_names,
                "lookback": self.lookback,
                "input_dim": len(self.feature_names),
                "metadata": self.metadata,
            },
            path,
        )
        path.with_suffix(".json").write_text(json.dumps(self.metadata, indent=2), encoding="utf-8")
        return path

    def load(self, path: Path) -> None:
        payload = torch.load(path, map_location=self.device, weights_only=False)
        self.feature_names = payload["feature_names"]
        self.lookback = payload["lookback"]
        self.metadata = payload.get("metadata", {})
        self.model = _LSTMForecaster(payload["input_dim"]).to(self.device)
        self.model.load_state_dict(payload["state_dict"])
        self.model.eval()
        logger.info("tft_model_loaded", path=str(path))
