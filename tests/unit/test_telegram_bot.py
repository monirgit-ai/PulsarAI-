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
