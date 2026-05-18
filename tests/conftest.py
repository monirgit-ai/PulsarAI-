import os

import pytest

# Ensure tests never use real Telegram or Binance
os.environ.setdefault("TELEGRAM_ALERTS_ENABLED", "false")
os.environ.setdefault("PAPER_TRADING", "true")
os.environ.setdefault("ENVIRONMENT", "development")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
