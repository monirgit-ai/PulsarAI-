import numpy as np

from models.rl_env import TradingEnv


def test_trading_env_steps() -> None:
    n = 200
    features = np.random.randn(n, 5).astype(np.float32)
    prices = np.linspace(100, 110, n).astype(np.float64)
    env = TradingEnv(features, prices)
    obs, _ = env.reset()
    assert obs.shape[0] == 8
    total_reward = 0.0
    for _ in range(10):
        obs, reward, term, trunc, _ = env.step(env.action_space.sample())
        total_reward += reward
        if term:
            break
    assert np.isfinite(total_reward)
