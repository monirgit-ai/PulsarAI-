"""Trading fee optimization helpers."""

from __future__ import annotations

from config.settings import settings

TAKER_FEE_PCT = 0.00075
MAKER_FEE_PCT = 0.0


class FeeOptimizer:
    """Prefer maker orders when possible; enforce minimum trade economics."""

    def __init__(
        self,
        taker_fee_pct: float = TAKER_FEE_PCT,
        maker_fee_pct: float = MAKER_FEE_PCT,
        min_trade_usdt: float | None = None,
    ) -> None:
        self.taker_fee_pct = taker_fee_pct
        self.maker_fee_pct = maker_fee_pct
        self.min_trade_usdt = min_trade_usdt or settings.min_trade_size_usdt

    def estimate_fee(self, notional_usdt: float, *, is_maker: bool = False) -> float:
        rate = self.maker_fee_pct if is_maker else self.taker_fee_pct
        return notional_usdt * rate

    def fee_impact_pct(self, notional_usdt: float) -> float:
        if notional_usdt <= 0:
            return 1.0
        return self.estimate_fee(notional_usdt) / notional_usdt

    def is_economical(self, notional_usdt: float, max_fee_impact_pct: float = 0.003) -> bool:
        if notional_usdt < self.min_trade_usdt:
            return False
        return self.fee_impact_pct(notional_usdt) <= max_fee_impact_pct

    def recommend_order_type(self, side: str, urgency: str = "entry") -> str:
        if urgency == "entry":
            return "MARKET"
        return "LIMIT"
