"""Persist trades and orders to TimescaleDB."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

import structlog

from data.storage import timescale
from execution.models import ExecutionResult, ManagedOrder, OrderStatus

logger = structlog.get_logger(__name__)


class TradeRepository:
    INSERT_TRADE = """
        INSERT INTO trades (
            opened_at, symbol, side, entry_price, quantity,
            fees_paid, stop_loss, take_profit, signals_used, status
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10)
        RETURNING id
    """

    UPDATE_CLOSE = """
        UPDATE trades SET
            closed_at = $2,
            exit_price = $3,
            pnl_usdt = $4,
            pnl_pct = $5,
            fees_paid = fees_paid + $6,
            status = 'CLOSED'
        WHERE id = $1
    """

    async def insert_open_trade(self, order: ManagedOrder, result: ExecutionResult) -> UUID:
        pool = await timescale.get_pool()
        signals = result.metadata.get("signal_metadata", {})
        async with pool.acquire() as conn:
            trade_id = await conn.fetchval(
                self.INSERT_TRADE,
                result.filled_at or datetime.now(timezone.utc),
                result.symbol,
                "LONG" if result.side == "BUY" else "SHORT",
                result.fill_price,
                result.filled_quantity,
                result.fee_usdt,
                order.stop_loss,
                order.take_profit,
                json.dumps(signals),
                "OPEN",
            )
        logger.info("trade_recorded_open", trade_id=str(trade_id), symbol=result.symbol)
        return trade_id

    async def close_trade(
        self,
        trade_id: UUID,
        exit_price: float,
        pnl_usdt: float,
        pnl_pct: float,
        fee_usdt: float,
    ) -> None:
        pool = await timescale.get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                self.UPDATE_CLOSE,
                trade_id,
                datetime.now(timezone.utc),
                exit_price,
                pnl_usdt,
                pnl_pct,
                fee_usdt,
            )
        logger.info("trade_recorded_closed", trade_id=str(trade_id), pnl_usdt=pnl_usdt)

    async def list_open_trades(self) -> list[dict]:
        pool = await timescale.get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, symbol, side, entry_price, quantity, stop_loss, take_profit, opened_at "
                "FROM trades WHERE status = 'OPEN' ORDER BY opened_at DESC"
            )
        return [dict(r) for r in rows]

    async def log_order_transition(
        self,
        order: ManagedOrder,
        new_status: OrderStatus,
    ) -> None:
        order.transitions.append((new_status, datetime.now(timezone.utc)))
        order.status = new_status
        logger.info(
            "order_state_transition",
            order_id=order.id,
            symbol=order.symbol,
            status=new_status.value,
        )
