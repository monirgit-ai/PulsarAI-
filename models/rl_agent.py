"""PPO reinforcement learning agent via Stable-Baselines3."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import structlog
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv

from data.processing.features import calculate_features
from models.common import artifact_path
from models.rl_env import TradingEnv

logger = structlog.get_logger(__name__)

ACTION_TO_SCORE = {
    0: 0.0,
    1: 0.25,
    2: 0.5,
    3: 1.0,
    4: -0.25,
    5: -0.5,
    6: -1.0,
}


class RLTradingAgent:
    def __init__(self, symbol: str = "BTCUSDT") -> None:
        self.symbol = symbol.upper()
        self.model: PPO | None = None
        self.feature_names: list[str] = []
        self.metadata: dict = {}

    def _build_env(self, ohlcv: pd.DataFrame) -> TradingEnv:
        featured = calculate_features(ohlcv).dropna()
        aligned = ohlcv.loc[featured.index]
        features = featured.values.astype(np.float32)
        prices = aligned["close"].values.astype(np.float64)
        self.feature_names = list(featured.columns)
        return TradingEnv(features, prices)

    def train(self, ohlcv: pd.DataFrame, timesteps: int = 50_000) -> dict:
        env = DummyVecEnv([lambda: self._build_env(ohlcv)])

        self.model = PPO(
            "MlpPolicy",
            env,
            learning_rate=3e-4,
            n_steps=2048,
            batch_size=64,
            gamma=0.99,
            verbose=0,
        )
        self.model.learn(total_timesteps=timesteps)

        self.metadata = {
            "symbol": self.symbol,
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "timesteps": timesteps,
            "features": self.feature_names,
        }
        logger.info("rl_agent_trained", **self.metadata)
        return self.metadata

    def predict_action(self, ohlcv: pd.DataFrame) -> tuple[int, float]:
        if self.model is None:
            raise RuntimeError("Model not trained or loaded")
        env = self._build_env(ohlcv)
        obs, _ = env.reset()
        action, _ = self.model.predict(obs, deterministic=True)
        action_id = int(action)
        return action_id, ACTION_TO_SCORE.get(action_id, 0.0)

    def save(self, path: Path | None = None) -> Path:
        if self.model is None:
            raise RuntimeError("No model to save")
        path = path or artifact_path("rl", self.symbol)
        model_path = path.with_suffix(".zip")
        self.model.save(str(model_path))
        meta = path.with_suffix(".json")
        meta.write_text(json.dumps(self.metadata, indent=2), encoding="utf-8")
        return model_path

    def load(self, path: Path) -> None:
        self.model = PPO.load(str(path))
        meta_path = path.with_suffix(".json")
        if meta_path.exists():
            self.metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        logger.info("rl_agent_loaded", path=str(path))
