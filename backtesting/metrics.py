"""Backtest performance metrics and validation gates."""

from __future__ import annotations

import math
from datetime import datetime

import numpy as np

from backtesting.models import TradeRecord

# Gate thresholds (Phase 2 minimum — stricter targets in project plan)
GATE_MIN_SHARPE = 1.0
GATE_MAX_DRAWDOWN_PCT = 20.0
GATE_MIN_PROFIT_FACTOR = 1.0


def compute_metrics(
    equity_curve: list[tuple[datetime, float]],
    trades: list[TradeRecord],
    initial_capital: float,
) -> dict[str, float]:
    if not equity_curve:
        return {}

    equities = np.array([e for _, e in equity_curve], dtype=float)
    returns = np.diff(equities) / equities[:-1]
    returns = returns[np.isfinite(returns)]

    total_return_pct = (equities[-1] / initial_capital - 1) * 100
    cagr = _cagr(equity_curve, initial_capital)
    sharpe = _sharpe(returns)
    sortino = _sortino(returns)
    max_dd_pct = _max_drawdown_pct(equities)
    calmar = (cagr / max_dd_pct * 100) if max_dd_pct > 0 else 0.0

    winners = [t for t in trades if t.pnl_usdt > 0]
    losers = [t for t in trades if t.pnl_usdt <= 0]
    win_rate = (len(winners) / len(trades) * 100) if trades else 0.0
    gross_profit = sum(t.pnl_usdt for t in winners)
    gross_loss = abs(sum(t.pnl_usdt for t in losers))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit or 0.0)

    avg_duration = float(np.mean([t.bars_held for t in trades])) if trades else 0.0
    months = max(_months_span(equity_curve), 1e-6)
    trades_per_month = len(trades) / months

    return {
        "total_return_pct": round(total_return_pct, 4),
        "cagr_pct": round(cagr, 4),
        "sharpe_ratio": round(sharpe, 4),
        "sortino_ratio": round(sortino, 4),
        "max_drawdown_pct": round(max_dd_pct, 4),
        "calmar_ratio": round(calmar, 4),
        "win_rate_pct": round(win_rate, 4),
        "profit_factor": round(profit_factor, 4),
        "trade_count": float(len(trades)),
        "avg_trade_bars": round(avg_duration, 2),
        "trades_per_month": round(trades_per_month, 4),
        "final_equity": round(float(equities[-1]), 2),
    }


def evaluate_gate(metrics: dict[str, float]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    sharpe = metrics.get("sharpe_ratio", 0.0)
    max_dd = metrics.get("max_drawdown_pct", 100.0)
    pf = metrics.get("profit_factor", 0.0)

    if sharpe < GATE_MIN_SHARPE:
        reasons.append(f"Sharpe {sharpe:.2f} < {GATE_MIN_SHARPE}")
    if max_dd > GATE_MAX_DRAWDOWN_PCT:
        reasons.append(f"Max drawdown {max_dd:.2f}% > {GATE_MAX_DRAWDOWN_PCT}%")
    if pf < GATE_MIN_PROFIT_FACTOR:
        reasons.append(f"Profit factor {pf:.2f} < {GATE_MIN_PROFIT_FACTOR}")

    return len(reasons) == 0, reasons


def _cagr(equity_curve: list[tuple[datetime, float]], initial: float) -> float:
    if len(equity_curve) < 2:
        return 0.0
    start, end = equity_curve[0][0], equity_curve[-1][0]
    years = (end - start).total_seconds() / (365.25 * 24 * 3600)
    if years <= 0:
        return 0.0
    final = equity_curve[-1][1]
    return ((final / initial) ** (1 / years) - 1) * 100


def _sharpe(returns: np.ndarray, periods_per_year: float = 365 * 24) -> float:
    """Sharpe for hourly bars by default."""
    if len(returns) < 2:
        return 0.0
    std = returns.std()
    if std == 0 or not math.isfinite(std):
        return 0.0
    return float(returns.mean() / std * math.sqrt(periods_per_year))


def _sortino(returns: np.ndarray, periods_per_year: float = 365 * 24) -> float:
    if len(returns) < 2:
        return 0.0
    downside = returns[returns < 0]
    if len(downside) == 0:
        return 0.0
    std = downside.std()
    if std == 0:
        return 0.0
    return float(returns.mean() / std * math.sqrt(periods_per_year))


def _max_drawdown_pct(equities: np.ndarray) -> float:
    peak = equities[0]
    max_dd = 0.0
    for eq in equities:
        peak = max(peak, eq)
        dd = (peak - eq) / peak * 100 if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
    return max_dd


def _months_span(equity_curve: list[tuple[datetime, float]]) -> float:
    if len(equity_curve) < 2:
        return 0.0
    delta = equity_curve[-1][0] - equity_curve[0][0]
    return delta.total_seconds() / (30.44 * 24 * 3600)
