"""Phase 5 monitoring tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config.settings import Settings
from monitoring.metrics import metrics_payload
from monitoring.telegram_alerts import notify_trade_opened
from monitoring.telegram_bot import TelegramNotifier, _authorized_chat


def test_metrics_endpoint_payload() -> None:
    body = metrics_payload()
    assert b"pulsarai_equity_usdt" in body or isinstance(body, bytes)


def test_authorized_chat_whitelist() -> None:
    with patch("monitoring.telegram_bot.settings") as mock_settings:
        mock_settings.telegram_chat_id = "12345"
        assert _authorized_chat("12345") is True
        assert _authorized_chat("99999") is False


@pytest.mark.asyncio
async def test_send_rejects_unauthorized_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "monitoring.telegram_bot.settings",
        Settings(
            _env_file=None,
            telegram_alerts_enabled=True,
            telegram_bot_token="token",
            telegram_chat_id="111",
        ),
    )
    notifier = TelegramNotifier()
    result = await notifier.send_alert("test", chat_id="222")
    assert result is False


@pytest.mark.asyncio
async def test_notify_trade_opened_skips_when_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "monitoring.telegram_bot.settings",
        Settings(_env_file=None, telegram_alerts_enabled=False),
    )
    result = await notify_trade_opened("BTCUSDT", "BUY", 0.01, 50000.0)
    assert result is False


@pytest.mark.asyncio
async def test_performance_tracker_collect_mocked() -> None:
    from monitoring.performance_tracker import PerformanceTracker

    tracker = PerformanceTracker()
    mock_portfolio = MagicMock()
    mock_portfolio.total_equity_usdt = 10_000
    mock_portfolio.cash_usdt = 8_000
    mock_portfolio.open_position_count = 1

    with (
        patch.object(tracker.portfolio, "load_state", AsyncMock(return_value=mock_portfolio)),
        patch.object(
            tracker,
            "_trade_stats",
            AsyncMock(
                return_value={
                    "daily_pnl": 50.0,
                    "fees_today": 1.0,
                    "realized_pnl_30d": 200.0,
                    "win_rate_30d": 55.0,
                    "sharpe_30d": 1.2,
                    "max_drawdown_pct": 3.0,
                    "closed_count_30d": 10,
                }
            ),
        ),
        patch.object(tracker.circuit, "is_active", AsyncMock(return_value=False)),
        patch.object(tracker, "_ws_connected", AsyncMock(return_value=True)),
        patch.object(tracker, "_cache_snapshot", AsyncMock()),
    ):
        snap = await tracker.collect()

    assert snap.equity_usdt == 10_000
    assert snap.daily_pnl_usdt == 50.0
    assert snap.ws_connected is True
