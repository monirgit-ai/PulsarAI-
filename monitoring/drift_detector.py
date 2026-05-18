"""Lightweight model/feature drift detection."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import structlog

from config.settings import settings
from data.storage import redis_cache, timescale
from monitoring import metrics as prom
from monitoring.telegram_alerts import notify_drift_detected

logger = structlog.get_logger(__name__)

REDIS_BASELINE = "pulsarai:drift:baseline"
DRIFT_THRESHOLD = 0.35


class DriftDetector:
    """Compare recent signal distribution vs stored baseline."""

    async def check_signal_drift(self) -> bool:
        """Returns True if drift was detected and alert sent."""
        pool = await timescale.get_pool()
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT direction, COUNT(*) AS cnt
                FROM signals
                WHERE time >= $1 AND direction IS NOT NULL
                GROUP BY direction
                """,
                since,
            )

        if not rows:
            logger.info("drift_check_skipped", reason="no_recent_signals")
            return False

        total = sum(int(r["cnt"]) for r in rows)
        dist = {str(r["direction"]): int(r["cnt"]) / total for r in rows}
        score = await self._drift_score(dist)

        prom.DRIFT_SCORE.set(score)
        if score < DRIFT_THRESHOLD:
            await self._save_baseline(dist)
            return False

        prev = await self._load_baseline()
        details = f"24h distribution: {dist}. Baseline: {prev or 'none'}."
        await notify_drift_detected(
            "signal_distribution",
            score,
            details,
            previous_score=None if not prev else await self._score_vs_baseline(dist, prev),
        )
        logger.warning("drift_detected", score=score, distribution=dist)
        return True

    async def _drift_score(self, current: dict[str, float]) -> float:
        baseline = await self._load_baseline()
        if not baseline:
            return 0.0
        return await self._score_vs_baseline(current, baseline)

    async def _score_vs_baseline(self, current: dict[str, float], baseline: dict[str, float]) -> float:
        keys = set(current) | set(baseline)
        return sum(abs(current.get(k, 0) - baseline.get(k, 0)) for k in keys) / max(len(keys), 1)

    async def _load_baseline(self) -> dict[str, float] | None:
        redis = await redis_cache.get_redis()
        raw = await redis.get(REDIS_BASELINE)
        if not raw:
            return None
        text = raw.decode() if isinstance(raw, bytes) else raw
        return json.loads(text)

    async def _save_baseline(self, dist: dict[str, float]) -> None:
        redis = await redis_cache.get_redis()
        await redis.set(REDIS_BASELINE, json.dumps(dist), ex=86400 * 14)
