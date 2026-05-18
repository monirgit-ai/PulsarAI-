"""Sentiment data collection and aggregation."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import structlog

from config.settings import settings
from data.storage import redis_cache

logger = structlog.get_logger(__name__)

FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=1"
CRYPTOPANIC_URL = "https://cryptopanic.com/api/v1/posts/"


async def fetch_fear_greed_index() -> float:
    """Return Fear & Greed value normalized to [-1, 1]."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(FEAR_GREED_URL)
        response.raise_for_status()
        data = response.json()
        value = int(data["data"][0]["value"])
        return (value - 50) / 50.0


async def fetch_cryptopanic_headlines(symbol: str, limit: int = 10) -> list[str]:
    if not settings.cryptopanic_api_key:
        return []
    params = {
        "auth_token": settings.cryptopanic_api_key,
        "currencies": symbol.replace("USDT", ""),
        "public": "true",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(CRYPTOPANIC_URL, params=params)
        response.raise_for_status()
        results = response.json().get("results", [])
        return [r.get("title", "") for r in results[:limit] if r.get("title")]


async def fetch_binance_funding_rate(symbol: str) -> float | None:
    """Funding rate from Binance futures (sentiment proxy). Returns rate or None."""
    sym = symbol.upper()
    if not sym.endswith("USDT"):
        sym = f"{sym}USDT"
    url = "https://fapi.binance.com/fapi/v1/premiumIndex"
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url, params={"symbol": sym})
        if response.status_code != 200:
            return None
        data = response.json()
        rate = float(data.get("lastFundingRate", 0))
        return max(-1.0, min(1.0, rate * 1000))


async def aggregate_sentiment(symbol: str) -> dict[str, float | str]:
    """Combine external sentiment sources into one score."""
    from models.sentiment_model import FinBertSentimentScorer

    components: dict[str, float] = {}
    texts: list[str] = []

    try:
        components["fear_greed"] = await fetch_fear_greed_index()
    except Exception:
        logger.exception("fear_greed_fetch_failed")
        components["fear_greed"] = 0.0

    try:
        headlines = await fetch_cryptopanic_headlines(symbol)
        texts.extend(headlines)
    except Exception:
        logger.exception("cryptopanic_fetch_failed")

    try:
        funding = await fetch_binance_funding_rate(symbol)
        if funding is not None:
            components["funding_rate"] = funding
    except Exception:
        logger.exception("funding_rate_fetch_failed")

    news_score = 0.0
    if texts:
        scorer = FinBertSentimentScorer()
        scores = [scorer.score_text(t) for t in texts[:10]]
        news_score = sum(scores) / len(scores) if scores else 0.0
    components["news"] = news_score

    weights = {"fear_greed": 0.25, "news": 0.45, "funding_rate": 0.30}
    total_w = sum(weights.get(k, 0) for k in components)
    combined = sum(components[k] * weights.get(k, 0) for k in components) / max(total_w, 1e-9)
    combined = max(-1.0, min(1.0, combined))

    payload = {
        "symbol": symbol.upper(),
        "score": combined,
        "components": components,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        redis = await redis_cache.get_redis()
        key = f"pulsarai:sentiment:{symbol.upper()}"
        await redis.set(key, json.dumps(payload), ex=900)
    except Exception:
        logger.exception("sentiment_redis_cache_failed")

    return payload
