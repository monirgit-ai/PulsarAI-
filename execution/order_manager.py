"""Order lifecycle manager — Signal → Risk → Execute → DB."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog

from backtesting.models import Signal, SignalAction
from config.settings import settings
from execution.binance_executor import BinanceExecutor, OrderExecutionError
from execution.fee_optimizer import FeeOptimizer
from execution.models import ManagedOrder, OrderStatus
from execution.paper_executor import PaperExecutor
from execution.trade_repository import TradeRepository
from risk.models import OrderRequest, OrderSide, PortfolioState
from risk.position_sizer import PositionSizer
from risk.risk_manager import RiskManager

logger = structlog.get_logger(__name__)


class OrderManager:
    def __init__(
        self,
        risk_manager: RiskManager | None = None,
        position_sizer: PositionSizer | None = None,
        trade_repo: TradeRepository | None = None,
    ) -> None:
        self.risk = risk_manager or RiskManager()
        self.sizer = position_sizer or PositionSizer()
        self.trades = trade_repo or TradeRepository()
        self.paper = PaperExecutor()
        self.live = BinanceExecutor()
        self.fees = FeeOptimizer()

    async def process_signal(
        self,
        signal: Signal,
        portfolio: PortfolioState,
        market_price: float,
        atr: float | None = None,
        return_correlations: dict[str, float] | None = None,
    ) -> ManagedOrder | None:
        if signal.action == SignalAction.HOLD:
            return None

        symbol = signal.symbol.upper()

        if signal.action == SignalAction.SELL:
            pos = portfolio.open_positions.get(symbol)
            if not pos:
                return None
            qty = pos.quantity * min(max(signal.size_pct, 0.0), 1.0)
            order_req = OrderRequest(
                symbol=symbol,
                side=OrderSide.SELL,
                quantity=qty,
                price=market_price,
                signal_metadata=signal.metadata,
            )
            return await self._execute(order_req, portfolio, market_price, return_correlations)

        if atr is None or atr <= 0:
            logger.warning("missing_atr_for_sizing", symbol=symbol)
            return None

        qty = self.sizer.size_from_atr(portfolio, symbol, market_price, atr)
        if qty <= 0:
            logger.warning("zero_position_size", symbol=symbol)
            return None

        stop = self.sizer.stop_loss_price(market_price, atr, OrderSide.BUY)
        tp = self.sizer.take_profit_price(market_price, stop, OrderSide.BUY)

        order_req = OrderRequest(
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=qty,
            price=market_price,
            stop_loss=stop,
            take_profit=tp,
            signal_metadata=signal.metadata,
        )
        return await self._execute(order_req, portfolio, market_price, return_correlations)

    async def _execute(
        self,
        order_req: OrderRequest,
        portfolio: PortfolioState,
        market_price: float,
        return_correlations: dict[str, float] | None,
    ) -> ManagedOrder | None:
        approved, rejection = await self.risk.validate_order(
            order_req, portfolio, return_correlations=return_correlations
        )
        if not approved:
            managed = ManagedOrder(
                id=str(uuid.uuid4()),
                symbol=order_req.symbol,
                side=order_req.side.value,
                quantity=order_req.quantity,
                status=OrderStatus.REJECTED,
            )
            managed.status = OrderStatus.REJECTED
            await self.trades.log_order_transition(managed, OrderStatus.REJECTED)
            return managed

        notional = order_req.quantity * (order_req.price or market_price)
        if not self.fees.is_economical(notional):
            logger.warning("order_uneconomical_fees", notional=notional)
            return None

        managed = ManagedOrder(
            id=str(uuid.uuid4()),
            symbol=order_req.symbol,
            side=order_req.side.value,
            quantity=order_req.quantity,
            status=OrderStatus.PENDING,
            stop_loss=order_req.stop_loss,
            take_profit=order_req.take_profit,
        )
        await self.trades.log_order_transition(managed, OrderStatus.PENDING)
        await self.trades.log_order_transition(managed, OrderStatus.SUBMITTED)

        try:
            if settings.paper_trading:
                result = await self.paper.execute_market_order(order_req, market_price)
            else:
                result = await self.live.execute_market_order(order_req, market_price)
        except OrderExecutionError as exc:
            logger.exception("execution_failed", error=str(exc))
            managed.status = OrderStatus.REJECTED
            await self.trades.log_order_transition(managed, OrderStatus.REJECTED)
            return managed

        result.metadata["signal_metadata"] = order_req.signal_metadata
        managed.filled_quantity = result.filled_quantity
        managed.entry_price = result.fill_price
        managed.fee_usdt = result.fee_usdt
        managed.status = OrderStatus.FILLED
        await self.trades.log_order_transition(managed, OrderStatus.FILLED)

        if order_req.side == OrderSide.BUY:
            trade_id = await self.trades.insert_open_trade(managed, result)
            managed.trade_db_id = trade_id
            if order_req.stop_loss and not settings.paper_trading:
                await self.live.place_stop_loss(
                    order_req.symbol,
                    result.filled_quantity,
                    order_req.stop_loss,
                )
        else:
            await self._close_position_trade(managed, result, portfolio)

        from monitoring.telegram_bot import send_alert

        await send_alert(
            f"Trade {result.side} {result.symbol}\n"
            f"Qty: {result.filled_quantity:.6f} @ {result.fill_price:.4f}\n"
            f"Fee: ${result.fee_usdt:.4f}\n"
            f"Mode: {'PAPER' if result.is_paper else 'LIVE'}",
            severity="INFO",
            module="order_manager",
            symbol=result.symbol,
        )

        return managed

    async def _close_position_trade(
        self,
        managed: ManagedOrder,
        result,
        portfolio: PortfolioState,
    ) -> None:
        open_trades = await self.trades.list_open_trades()
        match = next((t for t in open_trades if t["symbol"] == result.symbol), None)
        if not match:
            return
        entry = float(match["entry_price"])
        pnl = (result.fill_price - entry) * result.filled_quantity - result.fee_usdt
        pnl_pct = (result.fill_price / entry - 1) * 100 if entry else 0
        await self.trades.close_trade(
            match["id"],
            result.fill_price,
            pnl,
            pnl_pct,
            result.fee_usdt,
        )
