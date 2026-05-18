"""Combined AI signal generation using all model layers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import structlog

from backtesting.models import Signal
from models.ensemble import EnsembleAggregator
from models.regime_classifier import RegimeClassifier
from models.rl_agent import RLTradingAgent
from models.tft_model import TFTDirectionModel

logger = structlog.get_logger(__name__)


class AISignalGenerator:
    """Loads trained artifacts and produces ensemble trading signals."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol.upper()
        self.regime = RegimeClassifier(symbol)
        self.tft = TFTDirectionModel(symbol)
        self.rl = RLTradingAgent(symbol)
        self.ensemble = EnsembleAggregator()
        self._models_loaded = False

    def load_models(
        self,
        regime_path: Path | None = None,
        tft_path: Path | None = None,
        rl_path: Path | None = None,
    ) -> None:
        from models.common import ARTIFACTS_DIR

        if regime_path is None:
            regime_files = sorted(ARTIFACTS_DIR.glob(f"regime_{self.symbol}_*.pkl"))
            if not regime_files:
                raise FileNotFoundError(f"No regime model for {self.symbol}")
            regime_path = regime_files[-1]
        if tft_path is None:
            tft_files = sorted(ARTIFACTS_DIR.glob(f"tft_{self.symbol}_*.pt"))
            if not tft_files:
                raise FileNotFoundError(f"No TFT model for {self.symbol}")
            tft_path = tft_files[-1]
        if rl_path is None:
            rl_files = sorted(ARTIFACTS_DIR.glob(f"rl_{self.symbol}_*.zip"))
            if not rl_files:
                raise FileNotFoundError(f"No RL model for {self.symbol}")
            rl_path = rl_files[-1]

        self.regime.load(regime_path)
        self.tft.load(tft_path)
        self.rl.load(rl_path)
        self._models_loaded = True
        logger.info("ai_models_loaded", symbol=self.symbol)

    async def generate(
        self,
        ohlcv: pd.DataFrame,
        sentiment_score: float = 0.0,
    ) -> Signal:
        if not self._models_loaded:
            raise RuntimeError("Call load_models() first")

        regime_pred = self.regime.predict(ohlcv)
        tft_pred = self.tft.predict(ohlcv)
        _, rl_score = self.rl.predict_action(ohlcv)

        result = self.ensemble.aggregate(
            regime_score=self.regime.regime_score(regime_pred),
            tft_direction=tft_pred.direction,
            rl_score=rl_score,
            sentiment_score=sentiment_score,
            regime_confidence=regime_pred.confidence,
            tft_confidence=tft_pred.confidence,
        )

        signal = self.ensemble.to_signal(result, self.symbol)
        logger.info(
            "signal_generated",
            symbol=self.symbol,
            action=signal.action.value,
            score=result.final_score,
            components=result.components,
        )
        return signal
