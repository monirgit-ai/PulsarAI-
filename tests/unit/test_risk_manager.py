"""Unit tests for risk manager."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from risk.circuit_breaker import CircuitBreaker
from risk.models import OpenPosition, OrderRequest, OrderSide, PortfolioState
from risk.position_sizer import PositionSizer
from risk.risk_manager import RiskLimits, RiskManager


def _portfolio(
    cash: float = 10_000.0,
    equity: float = 10_000.0,
    positions: dict | None = None,
) -> PortfolioState:
    return PortfolioState(
        total_equity_usdt=equity,
        cash_usdt=cash,
        initial_equity_usdt=equity,
        daily_start_equity_usdt=equity,
        weekly_start_equity_usdt=equity,
        open_positions=positions or {},
    )


@pytest.fixture
def risk_manager() -> RiskManager:
    cb = MagicMock(spec=CircuitBreaker)
    cb.is_active = AsyncMock(return_value=False)
    cb.check_drawdown_limits = AsyncMock(return_value=None)
    limits = RiskLimits(
        max_position_risk_pct=0.02,
        max_open_positions=5,
        max_single_asset_pct=0.20,
        min_trade_size_usdt=50.0,
        usdt_reserve_pct=0.20,
    )
    return RiskManager(limits=limits, circuit_breaker=cb)


@pytest.mark.asyncio
async def test_approves_valid_buy(risk_manager: RiskManager) -> None:
    order = OrderRequest(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=0.001,
        price=60_000.0,
    )
    ok, rejection = await risk_manager.validate_order(order, _portfolio())
    assert ok is True
    assert rejection is None


@pytest.mark.asyncio
async def test_rejects_below_min_trade(risk_manager: RiskManager) -> None:
    order = OrderRequest(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=0.0001,
        price=10_000.0,
    )
    ok, rejection = await risk_manager.validate_order(order, _portfolio())
    assert ok is False
    assert rejection is not None
    assert rejection.limit_name == "min_trade_size_usdt"


@pytest.mark.asyncio
async def test_rejects_circuit_breaker(risk_manager: RiskManager) -> None:
    risk_manager.circuit_breaker.is_active = AsyncMock(return_value=True)
    risk_manager.circuit_breaker.get_reason = AsyncMock(return_value="test halt")
    order = OrderRequest(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=0.01,
        price=60_000.0,
    )
    ok, rejection = await risk_manager.validate_order(order, _portfolio())
    assert ok is False
    assert rejection is not None
    assert rejection.limit_name == "circuit_breaker"


@pytest.mark.asyncio
async def test_rejects_oversell(risk_manager: RiskManager) -> None:
    pos = OpenPosition(
        symbol="BTCUSDT",
        side="LONG",
        quantity=0.01,
        entry_price=50_000.0,
        notional_usdt=500.0,
        opened_at=datetime.now(timezone.utc),
    )
    portfolio = _portfolio(positions={"BTCUSDT": pos})
    order = OrderRequest(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        quantity=0.02,
        price=50_000.0,
    )
    ok, rejection = await risk_manager.validate_order(order, portfolio)
    assert ok is False
    assert rejection is not None
    assert rejection.limit_name == "position"


def test_position_sizer_atr() -> None:
    sizer = PositionSizer()
    portfolio = _portfolio(cash=5000, equity=10_000)
    qty = sizer.size_from_atr(portfolio, "BTCUSDT", 50_000.0, atr=500.0)
    assert qty > 0
    stop = sizer.stop_loss_price(50_000.0, 500.0, OrderSide.BUY)
    assert stop < 50_000.0
