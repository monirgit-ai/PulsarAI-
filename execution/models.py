"""Execution domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    OPEN = "OPEN"
    PARTIAL_FILL = "PARTIAL_FILL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass
class ExecutionResult:
    order_id: str
    symbol: str
    side: str
    status: OrderStatus
    filled_quantity: float
    fill_price: float
    fee_usdt: float
    is_paper: bool
    exchange_order_id: str | None = None
    filled_at: datetime | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ManagedOrder:
    id: str
    symbol: str
    side: str
    quantity: float
    status: OrderStatus
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    filled_quantity: float = 0.0
    fee_usdt: float = 0.0
    trade_db_id: UUID | None = None
    transitions: list[tuple[OrderStatus, datetime]] = field(default_factory=list)
