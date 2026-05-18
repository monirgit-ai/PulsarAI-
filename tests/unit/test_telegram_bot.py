import pytest

from config.settings import Settings
from monitoring.telegram_bot import AlertSeverity, TelegramNotifier


@pytest.mark.asyncio
async def test_send_alert_skipped_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "monitoring.telegram_bot.settings",
        Settings(_env_file=None, telegram_alerts_enabled=False),
    )
    result = await TelegramNotifier().send_alert("test", AlertSeverity.INFO)
    assert result is False


@pytest.mark.asyncio
async def test_rate_limit_blocks_after_max(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "monitoring.telegram_bot.settings",
        Settings(
            _env_file=None,
            telegram_alerts_enabled=True,
            telegram_bot_token="x",
            telegram_chat_id="1",
        ),
    )
    import time

    notifier = TelegramNotifier()
    now = time.time()
    notifier._hour_buckets["INFO"] = [now] * 10
    assert notifier._rate_limit_ok(AlertSeverity.INFO) is False
