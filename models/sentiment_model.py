"""FinBERT-based text sentiment scoring."""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

# Lazy load — heavy model
_pipeline = None


class FinBertSentimentScorer:
    """Scores text in [-1, 1] using ProsusAI/finbert."""

    def __init__(self, model_name: str = "ProsusAI/finbert") -> None:
        self.model_name = model_name

    def _get_pipeline(self):
        global _pipeline
        if _pipeline is None:
            from transformers import pipeline

            _pipeline = pipeline(
                "sentiment-analysis",
                model=self.model_name,
                tokenizer=self.model_name,
                truncation=True,
                max_length=512,
            )
            logger.info("finbert_loaded", model=self.model_name)
        return _pipeline

    def score_text(self, text: str) -> float:
        if not text or not text.strip():
            return 0.0
        try:
            pipe = self._get_pipeline()
            result = pipe(text[:512])[0]
            label = result["label"].lower()
            score = float(result["score"])
            if "positive" in label:
                return score
            if "negative" in label:
                return -score
            return 0.0
        except Exception:
            logger.exception("finbert_score_failed")
            return 0.0
