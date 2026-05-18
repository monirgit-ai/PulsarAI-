"""Core risk engine — single gate before any order reaches execution."""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from config.settings import settings
from risk.circuit_breaker import CircuitBreaker
from risk.models import OrderRequest, OrderSide, PortfolioState

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RiskLimits:
    max_position_risk_pct: float = 0.02
    max_open_positions: int = 5
    max_single_asset_pct: float = 0.20
    max_daily_drawdown_pct: float = 0.05
    max_weekly_drawdown_pct: float = 0.10
    max_correlation: float = 0.85
    min_trade_size_usdt: float = 50.0
    usdt_reserve_pct: float = 0.20


@dataclass(frozen=True)
class OrderRejection:
    reason: str
    limit_name: str
    attempted: dict
    limits: dict


class RiskManager:
    def __init__(
        self,
        limits: RiskLimits | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self.limits = limits or RiskLimits(
            max_position_risk_pct=settings.max_position_risk_pct,
            max_open_positions=settings.max_open_positions,
            max_single_asset_pct=settings.max_single_asset_pct,
            max_daily_drawdown_pct=settings.max_daily_drawdown_pct,
            max_weekly_drawdown_pct=settings.max_weekly_drawdown_pct,
            min_trade_size_usdt=settings.min_trade_size_usdt,
            usdt_reserve_pct=settings.usdt_reserve_pct,
        )
        self.circuit_breaker = circuit_breaker or CircuitBreaker()

    async def validate_order(
        self,
        order: OrderRequest,
        portfolio: PortfolioState,
        *,
        return_correlations: dict[str, float] | None = None,
    ) -> tuple[bool, OrderRejection | None]:
        """
        Validate order against ALL risk limits. Returns (True, None) if approved.
        """
        symbol = order.symbol.upper()
        limits_dict = {
            "max_position_risk_pct": self.limits.max_position_risk_pct,
            "max_open_positions": self.limits.max_open_positions,
            "max_single_asset_pct": self.limits.max_single_asset_pct,
            "max_daily_drawdown_pct": self.limits.max_daily_drawdown_pct,
            "max_weekly_drawdown_pct": self.limits.max_weekly_drawdown_pct,
            "max_correlation": self.limits.max_correlation,
            "min_trade_size_usdt": self.limits.min_trade_size_usdt,
            "usdt_reserve_pct": self.limits.usdt_reserve_pct,
        }

        if await self.circuit_breaker.is_active():
            reason = await self.circuit_breaker.get_reason() or "Circuit breaker active"
            return False, OrderRejection(
                reason=reason,
                limit_name="circuit_breaker",
                attempted={"symbol": symbol, "side": order.side.value},
                limits=limits_dict,
            )

        dd_reason = await self.circuit_breaker.check_drawdown_limits(portfolio.total_equity_usdt)
        if dd_reason:
            await self.circuit_breaker.trigger(dd_reason)
            return False, OrderRejection(
                reason=dd_reason,
                limit_name="drawdown",
                attempted={"equity": portfolio.total_equity_usdt},
                limits=limits_dict,
            )

        if order.side == OrderSide.BUY:
            if portfolio.open_position_count >= self.limits.max_open_positions:
                if symbol not in portfolio.open_positions:
                    return False, self._reject(
                        "Max open positions reached",
                        "max_open_positions",
                        {"count": portfolio.open_position_count},
                        limits_dict,
                    )

            notional = order.notional_usdt
            if notional < self.limits.min_trade_size_usdt:
                return False, self._reject(
                    f"Order size ${notional:.2f} below minimum",
                    "min_trade_size_usdt",
                    {"notional": notional},
                    limits_dict,
                )

            reserve = portfolio.total_equity_usdt * self.limits.usdt_reserve_pct
            if portfolio.cash_usdt - notional < reserve:
                return False, self._reject(
                    "Insufficient cash after USDT reserve",
                    "usdt_reserve_pct",
                    {"cash": portfolio.cash_usdt, "reserve": reserve, "notional": notional},
                    limits_dict,
                )

            if notional > portfolio.cash_usdt:
                return False, self._reject(
                    "Insufficient USDT balance",
                    "balance",
                    {"cash": portfolio.cash_usdt, "required": notional},
                    limits_dict,
                )

            risk_usdt = portfolio.total_equity_usdt * self.limits.max_position_risk_pct
            if notional > risk_usdt * 1.05:
                return False, self._reject(
                    f"Position risk exceeds {self.limits.max_position_risk_pct:.0%}",
                    "max_position_risk_pct",
                    {"notional": notional, "max_risk_usdt": risk_usdt},
                    limits_dict,
                )

            new_exposure = portfolio.symbol_exposure_usdt(symbol) + notional
            exposure_pct = new_exposure / max(portfolio.total_equity_usdt, 1e-9)
            if exposure_pct > self.limits.max_single_asset_pct:
                return False, self._reject(
                    f"Single-asset exposure {exposure_pct:.1%} exceeds limit",
                    "max_single_asset_pct",
                    {"symbol": symbol, "exposure_pct": exposure_pct},
                    limits_dict,
                )

            if return_correlations and portfolio.open_positions:
                for other_sym in portfolio.open_positions:
                    if other_sym == symbol:
                        continue
                    corr = return_correlations.get(other_sym, 0.0)
                    if abs(corr) >= self.limits.max_correlation:
                        return False, self._reject(
                            f"Correlation {corr:.2f} with {other_sym} too high",
                            "max_correlation",
                            {"symbol": symbol, "other": other_sym, "correlation": corr},
                            limits_dict,
                        )

        elif order.side == OrderSide.SELL:
            pos = portfolio.open_positions.get(symbol)
            if not pos or pos.quantity < order.quantity - 1e-12:
                return False, self._reject(
                    "Sell quantity exceeds open position",
                    "position",
                    {"requested": order.quantity, "held": pos.quantity if pos else 0},
                    limits_dict,
                )

        logger.info(
            "order_validated",
            symbol=symbol,
            side=order.side.value,
            quantity=order.quantity,
        )
        return True, None

    def _reject(
        self,
        reason: str,
        limit_name: str,
        attempted: dict,
        limits: dict,
    ) -> OrderRejection:
        rejection = OrderRejection(
            reason=reason,
            limit_name=limit_name,
            attempted=attempted,
            limits=limits,
        )
        logger.warning(
            "order_rejected",
            reason=reason,
            limit=limit_name,
            attempted=attempted,
        )
        return rejection
