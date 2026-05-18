"""Trading universe selection."""

from __future__ import annotations

import structlog
from binance import AsyncClient

from config.settings import settings

logger = structlog.get_logger(__name__)


async def fetch_top_usdt_pairs(limit: int | None = None) -> list[str]:
    """Return top USDT spot pairs by 24h quote volume."""
    cap = limit or settings.top_pairs_count
    client = await _create_client()
    try:
        tickers = await client.get_ticker()
        usdt = [
            t
            for t in tickers
            if t["symbol"].endswith("USDT")
            and not any(x in t["symbol"] for x in ("UP", "DOWN", "BULL", "BEAR"))
        ]
        usdt.sort(key=lambda x: float(x.get("quoteVolume", 0)), reverse=True)
        symbols = [t["symbol"] for t in usdt[:cap]]
        logger.info("universe_fetched", count=len(symbols), top=symbols[:5])
        return symbols
    finally:
        await client.close_connection()


async def _create_client() -> AsyncClient:
    if settings.binance_api_key and settings.binance_api_secret:
        return await AsyncClient.create(
            settings.binance_api_key,
            settings.binance_api_secret,
            testnet=settings.binance_testnet,
        )
    return await AsyncClient.create(testnet=settings.binance_testnet)


def parse_symbol_list(raw: str) -> list[str]:
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


def resolve_symbols() -> list[str]:
    if settings.trading_symbols.strip():
        return parse_symbol_list(settings.trading_symbols)
    return parse_symbol_list("BTCUSDT,ETHUSDT,BNBUSDT")
