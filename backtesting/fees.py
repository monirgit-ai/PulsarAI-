"""Fee and slippage models for backtesting."""

from __future__ import annotations

from backtesting.models import BacktestConfig


def slippage_pct(symbol: str, config: BacktestConfig) -> float:
    if symbol.upper() in config.large_cap_symbols:
        return config.slippage_large_cap_pct
    return config.slippage_alt_pct


def apply_slippage(price: float, side: str, slip_pct: float) -> float:
    """Worsen fill price by slippage (buy higher, sell lower)."""
    if side.upper() in ("BUY", "LONG"):
        return price * (1 + slip_pct)
    return price * (1 - slip_pct)


def trading_fee(notional: float, config: BacktestConfig, *, is_maker: bool = False) -> float:
    rate = config.maker_fee_pct if is_maker else config.taker_fee_pct
    return abs(notional) * rate


def max_fill_quantity(bar_volume: float, requested_qty: float, config: BacktestConfig) -> tuple[float, bool]:
    """Cap fill by fraction of bar volume; return (qty, is_partial)."""
    if bar_volume <= 0:
        return requested_qty, False
    cap = bar_volume * config.partial_fill_max_volume_pct
    if requested_qty > cap:
        return cap, True
    return requested_qty, False
