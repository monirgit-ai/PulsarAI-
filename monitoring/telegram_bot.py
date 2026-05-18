"""Telegram alert client — notifications only; must not block trading."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum

import httpx
import structlog

from config.settings import settings

logger = structlog.get_logger(__name__)

SEVERITY_ORDER = ("INFO", "WARNING", "CRITICAL")
MAX_ALERTS_PER_HOUR = 10


class AlertSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class TelegramNotifier:
    """Async Telegram sender with rate limiting and fail-safe behavior."""

    def __init__(self) -> None:
        self._hour_buckets: dict[str, list[float]] = defaultdict(list)

    def _rate_limit_ok(self, severity: AlertSeverity) -> bool:
        now = datetime.now(timezone.utc).timestamp()
        key = severity.value
        window = [t for t in self._hour_buckets[key] if now - t < 3600]
        self._hour_buckets[key] = window
        if len(window) >= MAX_ALERTS_PER_HOUR:
            return False
        window.append(now)
        return True

    def _format_message(
        self,
        message: str,
        severity: AlertSeverity,
        *,
        module: str | None = None,
        symbol: str | None = None,
        action: str | None = None,
    ) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        lines = [f"<b>[{severity.value}]</b> PulsarAI", f"<i>{ts}</i>", "", message]
        if module:
            lines.append(f"Module: <code>{module}</code>")
        if symbol:
            lines.append(f"Symbol: <code>{symbol}</code>")
        if severity == AlertSeverity.CRITICAL and action:
            lines.extend(["", f"<b>Action:</b> {action}"])
        return "\n".join(lines)

    async def send_alert(
        self,
        message: str,
        severity: AlertSeverity = AlertSeverity.INFO,
        *,
        module: str | None = None,
        symbol: str | None = None,
        action: str | None = None,
    ) -> bool:
        if not settings.telegram_configured:
            logger.debug("telegram_skipped", reason="not_configured")
            return False

        if not self._rate_limit_ok(severity):
            logger.warning("telegram_rate_limited", severity=severity.value)
            return False

        text = self._format_message(
            message,
            severity,
            module=module,
            symbol=symbol,
            action=action,
        )
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": settings.telegram_chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.post(url, json=payload)
                    response.raise_for_status()
                logger.info("telegram_sent", severity=severity.value, module=module)
                return True
            except Exception:
                logger.exception(
                    "telegram_send_failed",
                    attempt=attempt + 1,
                    severity=severity.value,
                )
                if attempt < 2:
                    await asyncio.sleep(2**attempt)

        return False


_notifier = TelegramNotifier()


async def send_alert(
    message: str,
    severity: str = "INFO",
    *,
    module: str | None = None,
    symbol: str | None = None,
    action: str | None = None,
) -> bool:
    """Send a Telegram alert; never raises."""
    try:
        sev = AlertSeverity(severity.upper())
    except ValueError:
        sev = AlertSeverity.INFO
    return await _notifier.send_alert(
        message,
        sev,
        module=module,
        symbol=symbol,
        action=action,
    )


async def notify_startup(environment: str, paper_trading: bool) -> bool:
    mode = "PAPER" if paper_trading else "LIVE"
    return await send_alert(
        f"PulsarAI started.\nEnvironment: {environment}\nMode: {mode}",
        severity="INFO",
        module="bot",
    )
