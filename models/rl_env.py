"""Gymnasium trading environment for RL agent."""

from __future__ import annotations

import gymnasium as gym
import numpy as np
from gymnasium import spaces


class TradingEnv(gym.Env):
    """
    Discrete actions:
    0 hold, 1 buy 5%, 2 buy 10%, 3 buy 20%,
    4 sell 25%, 5 sell 50%, 6 sell 100%
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        features: np.ndarray,
        prices: np.ndarray,
        initial_cash: float = 10_000.0,
        fee_pct: float = 0.00075,
    ) -> None:
        super().__init__()
        self.features = features.astype(np.float32)
        self.prices = prices.astype(np.float64)
        self.initial_cash = initial_cash
        self.fee_pct = fee_pct
        self.n_steps = len(features) - 1

        n_features = features.shape[1]
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(n_features + 3,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(7)

        self._cash = initial_cash
        self._position = 0.0
        self._step = 0

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        self._cash = self.initial_cash
        self._position = 0.0
        self._step = 0
        return self._obs(), {}

    def _obs(self) -> np.ndarray:
        feat = self.features[self._step]
        price = self.prices[self._step]
        equity = self._cash + self._position * price
        return np.concatenate(
            [
                feat,
                np.array(
                    [
                        self._cash / self.initial_cash,
                        self._position * price / max(equity, 1e-9),
                        equity / self.initial_cash,
                    ],
                    dtype=np.float32,
                ),
            ]
        )

    def step(self, action: int):
        price = self.prices[self._step]
        next_price = self.prices[self._step + 1]
        reward = 0.0

        if action == 1:
            self._buy(0.05, price)
        elif action == 2:
            self._buy(0.10, price)
        elif action == 3:
            self._buy(0.20, price)
        elif action == 4:
            self._sell(0.25, price)
        elif action == 5:
            self._sell(0.50, price)
        elif action == 6:
            self._sell(1.0, price)

        new_equity = self._cash + self._position * next_price
        old_equity = self._cash + self._position * price
        reward = (new_equity - old_equity) / self.initial_cash
        if action in (1, 2, 3, 4, 5, 6):
            reward -= self.fee_pct

        self._step += 1
        terminated = self._step >= self.n_steps - 1
        truncated = False
        return self._obs(), float(reward), terminated, truncated, {}

    def _buy(self, pct: float, price: float) -> None:
        if self._position > 0:
            return
        budget = self._cash * pct
        fee = budget * self.fee_pct
        qty = (budget - fee) / price
        if qty <= 0:
            return
        self._position += qty
        self._cash -= budget

    def _sell(self, pct: float, price: float) -> None:
        if self._position <= 0:
            return
        qty = self._position * pct
        proceeds = qty * price
        fee = proceeds * self.fee_pct
        self._cash += proceeds - fee
        self._position -= qty
