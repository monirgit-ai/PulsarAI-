"""Paper trading executor — simulated fills with realistic fees/slippage."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog

from backtesting.fees import apply_slippage, slippage_pct, trading_fee
from backtesting.models import BacktestConfig
from execution.models import ExecutionResult, OrderStatus
from risk.models import OrderRequest, OrderSide

logger = structlog.get_logger(__name__)


class PaperExecutor:
    def __init__(self) -> None:
        self._config = BacktestConfig()

    async def execute_market_order(
        self,
        order: OrderRequest,
        market_price: float,
    ) -> ExecutionResult:
        symbol = order.symbol.upper()
        slip = slippage_pct(symbol, self._config)
        side = "BUY" if order.side == OrderSide.BUY else "SELL"
        fill_price = apply_slippage(market_price, side, slip)
        notional = order.quantity * fill_price
        fee = trading_fee(notional, self._config)

        logger.info(
            "paper_order_filled",
            symbol=symbol,
            side=side,
            qty=order.quantity,
            price=fill_price,
            fee=fee,
        )

        return ExecutionResult(
            order_id=str(uuid.uuid4()),
            symbol=symbol,
            side=side,
            status=OrderStatus.FILLED,
            filled_quantity=order.quantity,
            fill_price=fill_price,
            fee_usdt=fee,
            is_paper=True,
            exchange_order_id=f"PAPER-{uuid.uuid4().hex[:8]}",
            filled_at=datetime.now(timezone.utc),
            metadata={"slippage_pct": slip},
        )
