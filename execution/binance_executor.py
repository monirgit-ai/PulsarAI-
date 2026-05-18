"""Live Binance spot order execution."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from binance import AsyncClient
from binance.exceptions import BinanceAPIException

from config.settings import settings
from execution.models import ExecutionResult, OrderStatus
from risk.models import OrderRequest, OrderSide

logger = structlog.get_logger(__name__)


class OrderExecutionError(Exception):
    pass


class BinanceExecutor:
    def __init__(self) -> None:
        self._client: AsyncClient | None = None

    async def _client_instance(self) -> AsyncClient:
        if self._client is None:
            if not settings.binance_api_key or not settings.binance_api_secret:
                raise OrderExecutionError("Binance API credentials not configured")
            self._client = await AsyncClient.create(
                settings.binance_api_key,
                settings.binance_api_secret,
                testnet=settings.binance_testnet,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close_connection()
            self._client = None

    async def execute_market_order(
        self,
        order: OrderRequest,
        market_price: float,
    ) -> ExecutionResult:
        if settings.paper_trading:
            raise OrderExecutionError("paper_trading=true — use PaperExecutor")

        client = await self._client_instance()
        symbol = order.symbol.upper()
        side = "BUY" if order.side == OrderSide.BUY else "SELL"

        try:
            if side == "BUY":
                quote_qty = order.quantity * market_price
                response = await client.order_market_buy(
                    symbol=symbol,
                    quoteOrderQty=round(quote_qty, 2),
                )
            else:
                response = await client.order_market_sell(
                    symbol=symbol,
                    quantity=self._format_qty(order.quantity),
                )
        except BinanceAPIException as exc:
            logger.error(
                "binance_order_failed",
                symbol=symbol,
                side=side,
                error_code=exc.code,
                error_message=exc.message,
            )
            raise OrderExecutionError(f"Binance order failed: {exc.message}") from exc

        fills = response.get("fills", [])
        filled_qty = sum(float(f["qty"]) for f in fills) if fills else float(response.get("executedQty", 0))
        fill_price = (
            sum(float(f["price"]) * float(f["qty"]) for f in fills) / filled_qty
            if fills and filled_qty > 0
            else market_price
        )
        fee = sum(float(f.get("commission", 0)) for f in fills) if fills else 0.0

        return ExecutionResult(
            order_id=str(uuid.uuid4()),
            symbol=symbol,
            side=side,
            status=OrderStatus.FILLED,
            filled_quantity=filled_qty,
            fill_price=fill_price,
            fee_usdt=fee,
            is_paper=False,
            exchange_order_id=str(response.get("orderId")),
            filled_at=datetime.now(timezone.utc),
        )

    async def place_stop_loss(
        self,
        symbol: str,
        quantity: float,
        stop_price: float,
    ) -> str | None:
        if settings.paper_trading:
            return f"PAPER-SL-{uuid.uuid4().hex[:6]}"
        client = await self._client_instance()
        try:
            response = await client.create_order(
                symbol=symbol.upper(),
                side="SELL",
                type="STOP_LOSS_LIMIT",
                timeInForce="GTC",
                quantity=self._format_qty(quantity),
                price=self._format_price(stop_price * 0.995),
                stopPrice=self._format_price(stop_price),
            )
            return str(response.get("orderId"))
        except BinanceAPIException as exc:
            logger.error("stop_loss_failed", symbol=symbol, error=exc.message)
            return None

    @staticmethod
    def _format_qty(qty: float) -> str:
        return f"{qty:.8f}".rstrip("0").rstrip(".")

    @staticmethod
    def _format_price(price: float) -> str:
        return f"{price:.8f}".rstrip("0").rstrip(".")
