"""Optional Telegram read-only commands: /status, /positions, /pnl."""

from __future__ import annotations

import structlog
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config.settings import settings
from execution.trade_repository import TradeRepository
from monitoring.performance_tracker import PerformanceTracker
from monitoring.telegram_bot import _authorized_chat

logger = structlog.get_logger(__name__)


def _reject_unauthorized(update: Update) -> bool:
    chat_id = str(update.effective_chat.id) if update.effective_chat else ""
    if not _authorized_chat(chat_id):
        logger.warning("telegram_unauthorized_command", chat_id=chat_id)
        return True
    return False


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if _reject_unauthorized(update) or update.message is None:
        return
    tracker = PerformanceTracker()
    snap = await tracker.collect()
    mode = "PAPER" if settings.paper_trading else "LIVE"
    text = (
        f"<b>PulsarAI Status</b> ({mode})\n"
        f"Environment: <code>{settings.environment}</code>\n"
        f"Equity: <code>${snap.equity_usdt:,.2f}</code>\n"
        f"Cash: <code>${snap.cash_usdt:,.2f}</code>\n"
        f"Open positions: <code>{snap.open_positions}</code>\n"
        f"Circuit breaker: <code>{'ACTIVE' if snap.circuit_breaker_active else 'off'}</code>\n"
        f"WebSocket: <code>{'connected' if snap.ws_connected else 'down'}</code>\n"
        f"Daily P&amp;L: <code>${snap.daily_pnl_usdt:,.2f}</code>"
    )
    await update.message.reply_html(text)


async def cmd_positions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if _reject_unauthorized(update) or update.message is None:
        return
    rows = await TradeRepository().list_open_trades()
    if not rows:
        await update.message.reply_html("<b>Open positions:</b> none")
        return
    lines = ["<b>Open positions:</b>"]
    for r in rows:
        lines.append(
            f"• <code>{r['symbol']}</code> {r['side']} "
            f"qty={float(r['quantity']):.6f} @ ${float(r['entry_price']):,.4f}"
        )
    await update.message.reply_html("\n".join(lines))


async def cmd_pnl(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if _reject_unauthorized(update) or update.message is None:
        return
    snap = await PerformanceTracker().collect()
    sign = "+" if snap.daily_pnl_usdt >= 0 else ""
    text = (
        f"<b>P&amp;L</b>\n"
        f"Today: <b>{sign}${snap.daily_pnl_usdt:,.2f}</b>\n"
        f"30d realized: <code>${snap.realized_pnl_30d:,.2f}</code>\n"
        f"Win rate (30d): <code>{snap.win_rate_30d:.1f}%</code>\n"
        f"Sharpe (30d): <code>{snap.sharpe_30d:.2f}</code>\n"
        f"Max drawdown: <code>{snap.max_drawdown_pct:.1f}%</code>\n"
        f"Fees today: <code>${snap.fees_today_usdt:,.4f}</code>"
    )
    await update.message.reply_html(text)


def build_application() -> Application:
    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .build()
    )
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("positions", cmd_positions))
    app.add_handler(CommandHandler("pnl", cmd_pnl))
    return app


async def run_command_bot() -> None:
    if not settings.telegram_commands_enabled or not settings.telegram_configured:
        logger.info("telegram_commands_disabled")
        return
    app = build_application()
    logger.info("telegram_commands_starting")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    try:
        while True:
            import asyncio

            await asyncio.sleep(3600)
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
