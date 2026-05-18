"""Ensemble signal aggregation across AI layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from backtesting.models import Signal, SignalAction

logger = structlog.get_logger(__name__)

DEFAULT_WEIGHTS = {
    "regime": 0.25,
    "tft": 0.35,
    "rl": 0.25,
    "sentiment": 0.15,
}

BUY_THRESHOLD = 0.25
SELL_THRESHOLD = -0.25


@dataclass
class EnsembleResult:
    final_score: float
    action: SignalAction
    confidence: float
    components: dict[str, float] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class EnsembleAggregator:
    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.weights = weights or DEFAULT_WEIGHTS.copy()
        total = sum(self.weights.values())
        if abs(total - 1.0) > 0.01:
            self.weights = {k: v / total for k, v in self.weights.items()}

    def aggregate(
        self,
        regime_score: float,
        tft_direction: float,
        rl_score: float,
        sentiment_score: float,
        *,
        regime_confidence: float = 1.0,
        tft_confidence: float = 1.0,
    ) -> EnsembleResult:
        components = {
            "regime": regime_score * regime_confidence,
            "tft": tft_direction * tft_confidence,
            "rl": rl_score,
            "sentiment": sentiment_score,
        }
        final = sum(components[k] * self.weights.get(k, 0) for k in components)
        final = max(-1.0, min(1.0, final))

        if final >= BUY_THRESHOLD:
            action = SignalAction.BUY
        elif final <= SELL_THRESHOLD:
            action = SignalAction.SELL
        else:
            action = SignalAction.HOLD

        confidence = min(1.0, abs(final))

        return EnsembleResult(
            final_score=final,
            action=action,
            confidence=confidence,
            components=components,
            weights=self.weights.copy(),
        )

    def to_signal(self, result: EnsembleResult, symbol: str, size_pct: float = 0.10) -> Signal:
        if result.action == SignalAction.HOLD:
            return Signal(SignalAction.HOLD, symbol, size_pct=0.0)
        return Signal(
            result.action,
            symbol,
            size_pct=size_pct if result.action == SignalAction.BUY else 1.0,
            metadata={
                "ensemble_score": result.final_score,
                "confidence": result.confidence,
                "components": result.components,
            },
        )

    def update_weights_from_accuracy(self, accuracy_by_source: dict[str, float]) -> None:
        """Adjust weights weekly based on recent signal accuracy (meta-learning stub)."""
        if not accuracy_by_source:
            return
        total = sum(max(0.01, v) for v in accuracy_by_source.values())
        for key in self.weights:
            if key in accuracy_by_source:
                self.weights[key] = max(0.05, accuracy_by_source[key] / total)
        norm = sum(self.weights.values())
        self.weights = {k: v / norm for k, v in self.weights.items()}
        logger.info("ensemble_weights_updated", weights=self.weights)
