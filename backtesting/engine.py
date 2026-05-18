"""Event-driven backtesting engine — bar-by-bar, no look-ahead."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd
import structlog

from backtesting import fees, metrics
from backtesting.models import (
    BacktestConfig,
    BacktestResult,
    Fill,
    Signal,
    SignalAction,
    TradeRecord,
)
from strategy.base import Strategy

logger = structlog.get_logger(__name__)


@dataclass
class _Position:
    quantity: float = 0.0
    avg_price: float = 0.0
    entry_time: datetime | None = None
    entry_bar: int = 0
    fees_paid: float = 0.0


@dataclass
class _Portfolio:
    cash: float
    positions: dict[str, _Position] = field(default_factory=dict)
    fills: list[Fill] = field(default_factory=list)
    closed_trades: list[TradeRecord] = field(default_factory=list)
    equity_curve: list[tuple[datetime, float]] = field(default_factory=list)

    def position(self, symbol: str) -> _Position:
        if symbol not in self.positions:
            self.positions[symbol] = _Position()
        return self.positions[symbol]

    def equity(self, prices: dict[str, float]) -> float:
        total = self.cash
        for sym, pos in self.positions.items():
            if pos.quantity > 0 and sym in prices:
                total += pos.quantity * prices[sym]
        return total


class BacktestEngine:
    """Processes OHLCV bars chronologically; signals execute on next bar open."""

    def __init__(self, config: BacktestConfig | None = None) -> None:
        self.config = config or BacktestConfig()

    def run(
        self,
        data: pd.DataFrame,
        strategy: Strategy,
        symbol: str,
        timeframe: str = "1h",
    ) -> BacktestResult:
        df = self._prepare_data(data)
        if len(df) < 2:
            raise ValueError("Need at least 2 bars for backtesting")

        symbol = symbol.upper()
        portfolio = _Portfolio(cash=self.config.initial_capital_usdt)
        pending_signal: Signal | None = None

        for i in range(len(df)):
            row = df.iloc[i]
            ts = df.index[i]
            if not isinstance(ts, datetime):
                ts = pd.Timestamp(ts).to_pydatetime()

            # Execute pending signal at this bar's open
            if pending_signal is not None and pending_signal.action != SignalAction.HOLD:
                self._execute_signal(
                    portfolio,
                    pending_signal,
                    open_price=float(row["open"]),
                    bar_volume=float(row["volume"]),
                    bar_time=ts,
                    bar_index=i,
                )
            pending_signal = None

            # Strategy sees history 0..i only (closed bar)
            history = df.iloc[: i + 1]
            signal = strategy.on_bar(i, history)
            if signal is not None and signal.action != SignalAction.HOLD:
                pending_signal = signal

            close_prices = {symbol: float(row["close"])}
            portfolio.equity_curve.append((ts, portfolio.equity(close_prices)))

        # Flatten at end
        pos = portfolio.position(symbol)
        if pos.quantity > 0:
            last = df.iloc[-1]
            ts_end = df.index[-1]
            if not isinstance(ts_end, datetime):
                ts_end = pd.Timestamp(ts_end).to_pydatetime()
            self._execute_signal(
                portfolio,
                Signal(SignalAction.SELL, symbol, size_pct=1.0),
                open_price=float(last["close"]),
                bar_volume=float(last["volume"]),
                bar_time=ts_end,
                bar_index=len(df) - 1,
            )
            portfolio.equity_curve.append((ts_end, portfolio.equity({symbol: float(last["close"])})))

        result_metrics = metrics.compute_metrics(
            portfolio.equity_curve,
            portfolio.closed_trades,
            self.config.initial_capital_usdt,
        )
        passed, reasons = metrics.evaluate_gate(result_metrics)

        return BacktestResult(
            config=self.config,
            symbol=symbol,
            timeframe=timeframe,
            start_time=portfolio.equity_curve[0][0],
            end_time=portfolio.equity_curve[-1][0],
            initial_capital=self.config.initial_capital_usdt,
            final_equity=portfolio.equity_curve[-1][1],
            trades=portfolio.closed_trades,
            equity_curve=portfolio.equity_curve,
            metrics=result_metrics,
            passed_gate=passed,
            gate_reasons=reasons,
        )

    def _prepare_data(self, data: pd.DataFrame) -> pd.DataFrame:
        required = {"open", "high", "low", "close", "volume"}
        missing = required - set(data.columns)
        if missing:
            raise ValueError(f"Missing columns: {missing}")
        df = data.copy()
        if not isinstance(df.index, pd.DatetimeIndex):
            if "time" in df.columns:
                df = df.set_index("time")
            else:
                raise ValueError("DataFrame needs DatetimeIndex or 'time' column")
        df = df.sort_index()
        return df

    def _execute_signal(
        self,
        portfolio: _Portfolio,
        signal: Signal,
        open_price: float,
        bar_volume: float,
        bar_time: datetime,
        bar_index: int,
    ) -> None:
        symbol = signal.symbol.upper()
        slip = fees.slippage_pct(symbol, self.config)
        pos = portfolio.position(symbol)

        if signal.action == SignalAction.BUY:
            if pos.quantity > 0:
                return
            equity = portfolio.equity({symbol: open_price})
            notional = equity * min(signal.size_pct, self.config.max_position_pct)
            if notional < self.config.min_trade_usdt:
                return
            fill_price = fees.apply_slippage(open_price, "BUY", slip)
            qty = notional / fill_price
            qty, partial = fees.max_fill_quantity(bar_volume, qty, self.config)
            cost = qty * fill_price
            fee = fees.trading_fee(cost, self.config)
            total = cost + fee
            if total > portfolio.cash:
                qty = (portfolio.cash * 0.99) / (fill_price * (1 + self.config.taker_fee_pct))
                cost = qty * fill_price
                fee = fees.trading_fee(cost, self.config)
                total = cost + fee
            if qty <= 0 or total > portfolio.cash:
                return

            portfolio.cash -= total
            pos.quantity = qty
            pos.avg_price = fill_price
            pos.entry_time = bar_time
            pos.entry_bar = bar_index
            pos.fees_paid = fee
            portfolio.fills.append(
                Fill(bar_time, symbol, "BUY", qty, fill_price, fee, slip, partial)
            )

        elif signal.action == SignalAction.SELL:
            if pos.quantity <= 0:
                return
            sell_qty = pos.quantity * min(max(signal.size_pct, 0.0), 1.0)
            sell_qty, partial = fees.max_fill_quantity(bar_volume, sell_qty, self.config)
            if sell_qty <= 0:
                return
            fill_price = fees.apply_slippage(open_price, "SELL", slip)
            proceeds = sell_qty * fill_price
            fee = fees.trading_fee(proceeds, self.config)
            portfolio.cash += proceeds - fee

            entry_price = pos.avg_price
            pnl = (fill_price - entry_price) * sell_qty - fee - (
                pos.fees_paid * (sell_qty / pos.quantity) if pos.quantity else 0
            )
            pnl_pct = (fill_price / entry_price - 1) * 100 if entry_price else 0.0

            portfolio.closed_trades.append(
                TradeRecord(
                    symbol=symbol,
                    side="LONG",
                    entry_time=pos.entry_time or bar_time,
                    exit_time=bar_time,
                    entry_price=entry_price,
                    exit_price=fill_price,
                    quantity=sell_qty,
                    pnl_usdt=pnl,
                    pnl_pct=pnl_pct,
                    fees_paid=fee + (pos.fees_paid * (sell_qty / pos.quantity) if pos.quantity else 0),
                    bars_held=bar_index - pos.entry_bar,
                )
            )
            portfolio.fills.append(
                Fill(bar_time, symbol, "SELL", sell_qty, fill_price, fee, slip, partial)
            )

            remaining = pos.quantity - sell_qty
            if remaining <= 1e-12:
                portfolio.positions.pop(symbol, None)
            else:
                pos.quantity = remaining
                pos.fees_paid *= remaining / (remaining + sell_qty)
