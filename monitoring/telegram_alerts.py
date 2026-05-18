"""Typed Telegram alerts for trading and system events."""

from __future__ import annotations

import html
import traceback
from typing import Any

import structlog

from monitoring.telegram_bot import AlertSeverity, send_alert

logger = structlog.get_logger(__name__)


def _esc(value: Any) -> str:
    return html.escape(str(value))


def _metrics_block(metrics: dict[str, Any] | None) -> str:
    if not metrics:
        return ""
    lines = ["", "<b>Metrics:</b>"]
    for key, val in metrics.items():
        lines.append(f"  • {_esc(key)}: <code>{_esc(val)}</code>")
    return "\n".join(lines)


async def notify_trade_opened(
    symbol: str,
    side: str,
    quantity: float,
    price: float,
    *,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    is_paper: bool = True,
    extra: dict[str, Any] | None = None,
) -> bool:
    mode = "PAPER" if is_paper else "LIVE"
    msg = (
        f"<b>Trade opened</b> ({mode})\n"
        f"Symbol: <code>{_esc(symbol)}</code>\n"
        f"Side: <code>{_esc(side)}</code>\n"
        f"Size: <code>{quantity:.6f}</code> @ <code>${price:,.4f}</code>"
    )
    if stop_loss:
        msg += f"\nStop-loss: <code>${stop_loss:,.4f}</code>"
    if take_profit:
        msg += f"\nTake-profit: <code>${take_profit:,.4f}</code>"
    msg += _metrics_block(extra)
    return await send_alert(msg, severity="INFO", module="execution", symbol=symbol)


async def notify_trade_closed(
    symbol: str,
    side: str,
    quantity: float,
    entry_price: float,
    exit_price: float,
    pnl_usdt: float,
    pnl_pct: float,
    *,
    is_paper: bool = True,
    extra: dict[str, Any] | None = None,
) -> bool:
    mode = "PAPER" if is_paper else "LIVE"
    sign = "+" if pnl_usdt >= 0 else ""
    msg = (
        f"<b>Trade closed</b> ({mode})\n"
        f"Symbol: <code>{_esc(symbol)}</code>\n"
        f"Side: <code>{_esc(side)}</code>\n"
        f"Qty: <code>{quantity:.6f}</code>\n"
        f"Entry: <code>${entry_price:,.4f}</code> → Exit: <code>${exit_price:,.4f}</code>\n"
        f"P&amp;L: <b>{sign}${pnl_usdt:,.2f}</b> ({sign}{pnl_pct:.2f}%)"
    )
    msg += _metrics_block(extra)
    severity = "INFO" if pnl_usdt >= 0 else "WARNING"
    return await send_alert(msg, severity=severity, module="execution", symbol=symbol)


async def notify_stop_loss_hit(
    symbol: str,
    quantity: float,
    stop_price: float,
    exit_price: float,
    pnl_usdt: float,
) -> bool:
    msg = (
        f"<b>Stop-loss triggered</b>\n"
        f"Symbol: <code>{_esc(symbol)}</code>\n"
        f"Qty: <code>{quantity:.6f}</code>\n"
        f"Stop: <code>${stop_price:,.4f}</code> | Fill: <code>${exit_price:,.4f}</code>\n"
        f"P&amp;L: <code>${pnl_usdt:,.2f}</code>"
    )
    return await send_alert(
        msg,
        severity="WARNING",
        module="risk",
        symbol=symbol,
        action="Review position sizing and market conditions.",
    )


async def notify_take_profit_hit(
    symbol: str,
    quantity: float,
    target_price: float,
    exit_price: float,
    pnl_usdt: float,
) -> bool:
    msg = (
        f"<b>Take-profit hit</b>\n"
        f"Symbol: <code>{_esc(symbol)}</code>\n"
        f"Qty: <code>{quantity:.6f}</code>\n"
        f"Target: <code>${target_price:,.4f}</code> | Fill: <code>${exit_price:,.4f}</code>\n"
        f"P&amp;L: <code>${pnl_usdt:,.2f}</code>"
    )
    return await send_alert(msg, severity="INFO", module="execution", symbol=symbol)


async def notify_circuit_breaker(reason: str, equity_usdt: float | None = None) -> bool:
    metrics = {"equity_usdt": f"${equity_usdt:,.2f}"} if equity_usdt is not None else None
    msg = f"<b>Circuit breaker ACTIVE</b>\n{_esc(reason)}"
    msg += _metrics_block(metrics)
    return await send_alert(
        msg,
        severity="CRITICAL",
        module="circuit_breaker",
        action="Trading halted. Manual review required before reset.",
    )


async def notify_drift_detected(
    drift_type: str,
    score: float,
    details: str,
    *,
    previous_score: float | None = None,
) -> bool:
    metrics: dict[str, Any] = {"drift_score": f"{score:.3f}"}
    if previous_score is not None:
        metrics["previous_score"] = f"{previous_score:.3f}"
    msg = f"<b>Model drift detected</b>\nType: <code>{_esc(drift_type)}</code>\n{_esc(details)}"
    msg += _metrics_block(metrics)
    return await send_alert(
        msg,
        severity="WARNING",
        module="drift_detector",
        action="Consider retraining models via train_models.py",
    )


async def notify_system_error(
    module: str,
    error: str,
    *,
    exc: BaseException | None = None,
) -> bool:
    tb = ""
    if exc is not None:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__, limit=3))
        tb = _esc(tb[-500:])
    msg = f"<b>System error</b>\nModule: <code>{_esc(module)}</code>\n{_esc(error)}"
    if tb:
        msg += f"\n\n<pre>{tb}</pre>"
    return await send_alert(
        msg,
        severity="CRITICAL",
        module=module,
        action="Check logs and service health immediately.",
    )


async def notify_daily_pnl_summary(
    *,
    equity_usdt: float,
    daily_pnl_usdt: float,
    realized_pnl_30d: float,
    win_rate_30d: float,
    sharpe_30d: float,
    open_positions: int,
    fees_today: float,
    paper_trading: bool,
) -> bool:
    mode = "PAPER" if paper_trading else "LIVE"
    sign = "+" if daily_pnl_usdt >= 0 else ""
    msg = (
        f"<b>Daily P&amp;L Summary</b> ({mode})\n"
        f"Equity: <code>${equity_usdt:,.2f}</code>\n"
        f"Today P&amp;L: <b>{sign}${daily_pnl_usdt:,.2f}</b>\n"
        f"30d realized: <code>${realized_pnl_30d:,.2f}</code>\n"
        f"Win rate (30d): <code>{win_rate_30d:.1f}%</code>\n"
        f"Sharpe (30d): <code>{sharpe_30d:.2f}</code>\n"
        f"Open positions: <code>{open_positions}</code>\n"
        f"Fees today: <code>${fees_today:,.4f}</code>"
    )
    return await send_alert(msg, severity="INFO", module="daily_summary")


async def safe_notify(coro) -> None:
    """Fire-and-forget wrapper — never raises into trading loop."""
    try:
        await coro
    except Exception:
        logger.exception("telegram_alert_failed")
