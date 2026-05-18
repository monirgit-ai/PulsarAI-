"""Shared model utilities and artifact paths."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

REGIME_LABELS = ("trending_up", "trending_down", "ranging", "volatile", "crash")

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"


def artifact_path(model_type: str, symbol: str, version: str | None = None) -> Path:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    ver = version or datetime.now(timezone.utc).strftime("%Y%m%d")
    safe_sym = symbol.replace("/", "_").upper()
    return ARTIFACTS_DIR / f"{model_type}_{safe_sym}_{ver}"
