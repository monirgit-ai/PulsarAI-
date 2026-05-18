"""Unit tests for execution layer."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backtesting.models import Signal, SignalAction
from execution.fee_optimizer import FeeOptimizer
from execution.models import OrderStatus
from execution.order_manager import OrderManager
from execution.paper_executor import PaperExecutor
from risk.models import OrderRequest, OrderSide, PortfolioState
from risk.risk_manager import RiskManager


def _portfolio(cash: float = 50_000.0) -> PortfolioState:
    return PortfolioState(
        total_equity_usdt=cash,
        cash_usdt=cash,
        initial_equity_usdt=cash,
        daily_start_equity_usdt=cash,
        weekly_start_equity_usdt=cash,
    )


@pytest.mark.asyncio
async def test_paper_executor_fills() -> None:
    executor = PaperExecutor()
    order = OrderRequest(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=0.01,
        price=50_000.0,
    )
    result = await executor.execute_market_order(order, 50_000.0)
    assert result.status == OrderStatus.FILLED
    assert result.filled_quantity == 0.01
    assert result.is_paper is True
    assert result.fee_usdt >= 0


def test_fee_optimizer_economical() -> None:
    opt = FeeOptimizer(min_trade_usdt=50.0)
    assert opt.is_economical(1000.0) is True
    assert opt.is_economical(10.0) is False


@pytest.mark.asyncio
async def test_order_manager_buy_flow() -> None:
    risk = MagicMock(spec=RiskManager)
    risk.validate_order = AsyncMock(return_value=(True, None))

    trades = MagicMock()
    trades.log_order_transition = AsyncMock()
    trades.insert_open_trade = AsyncMock(return_value="00000000-0000-0000-0000-000000000001")
    trades.list_open_trades = AsyncMock(return_value=[])

    manager = OrderManager(risk_manager=risk, trade_repo=trades)
    signal = Signal(action=SignalAction.BUY, symbol="BTCUSDT", size_pct=1.0)
    order = await manager.process_signal(
        signal,
        _portfolio(),
        market_price=50_000.0,
        atr=500.0,
    )
    assert order is not None
    assert order.status == OrderStatus.FILLED
    trades.insert_open_trade.assert_awaited_once()


@pytest.mark.asyncio
async def test_order_manager_rejects_risk() -> None:
    from risk.risk_manager import OrderRejection

    risk = MagicMock(spec=RiskManager)
    risk.validate_order = AsyncMock(
        return_value=(
            False,
            OrderRejection(
                reason="too big",
                limit_name="max_position_risk_pct",
                attempted={},
                limits={},
            ),
        )
    )
    trades = MagicMock()
    trades.log_order_transition = AsyncMock()

    manager = OrderManager(risk_manager=risk, trade_repo=trades)
    signal = Signal(action=SignalAction.BUY, symbol="BTCUSDT")
    order = await manager.process_signal(
        signal,
        _portfolio(),
        market_price=50_000.0,
        atr=500.0,
    )
    assert order is not None
    assert order.status == OrderStatus.REJECTED


@pytest.mark.asyncio
async def test_order_manager_hold_returns_none() -> None:
    manager = OrderManager()
    signal = Signal(action=SignalAction.HOLD, symbol="BTCUSDT")
    result = await manager.process_signal(signal, _portfolio(), 50_000.0, atr=500.0)
    assert result is None
