"""Binance WebSocket kline ingestion with auto-reconnect."""

from __future__ import annotations

import asyncio

import structlog
from binance import AsyncClient, BinanceSocketManager

from config.settings import settings
from data.ingestion.models import Candle
from data.ingestion.universe import resolve_symbols
from data.storage import candles as candle_store, redis_cache
from monitoring.telegram_bot import send_alert

logger = structlog.get_logger(__name__)


class KlineIngestionService:
    """Multiplexed kline WebSocket consumer."""

    def __init__(self) -> None:
        self._attempt = 0
        self._client: AsyncClient | None = None

    def _stream_names(self) -> list[str]:
        symbols = resolve_symbols()
        streams: list[str] = []
        for symbol in symbols:
            for interval in settings.ws_kline_interval_list:
                streams.append(f"{symbol.lower()}@kline_{interval}")
        return streams

    async def _set_ws_status(self, status: str) -> None:
        redis = await redis_cache.get_redis()
        await redis.set("pulsarai:ws:status", status, ex=3600)

    async def _handle_kline(self, kline: dict) -> None:
        if not kline.get("x"):
            # Only persist closed candles to avoid partial bar churn
            return
        candle = Candle.from_ws_kline(kline)
        await candle_store.upsert_candle(candle)
        await candle_store.cache_latest_candle(candle)

    async def _run_socket(self) -> None:
        if settings.binance_api_key and settings.binance_api_secret:
            self._client = await AsyncClient.create(
                settings.binance_api_key,
                settings.binance_api_secret,
                testnet=settings.binance_testnet,
            )
        else:
            self._client = await AsyncClient.create(testnet=settings.binance_testnet)

        bsm = BinanceSocketManager(self._client)
        streams = self._stream_names()
        logger.info("ws_subscribing", stream_count=len(streams), streams=streams[:6])

        async with bsm.multiplex_socket(streams) as stream:
            self._attempt = 0
            await self._set_ws_status("connected")
            await send_alert(
                f"WebSocket connected ({len(streams)} streams).",
                severity="INFO",
                module="binance_ws",
            )
            while True:
                msg = await stream.recv()
                if msg is None:
                    continue
                payload = msg.get("data", msg)
                kline = payload.get("k") if isinstance(payload, dict) else None
                if kline:
                    await self._handle_kline(kline)

    async def _close_client(self) -> None:
        if self._client is not None:
            await self._client.close_connection()
            self._client = None

    async def run_forever(self) -> None:
        while True:
            try:
                await self._run_socket()
            except asyncio.CancelledError:
                await self._set_ws_status("stopped")
                await self._close_client()
                raise
            except Exception as exc:
                self._attempt += 1
                delay = min(2**self._attempt, 60)
                await self._set_ws_status("disconnected")
                logger.exception("ws_disconnected", attempt=self._attempt, delay=delay)
                await send_alert(
                    f"WebSocket disconnected: {exc!s}\nReconnecting in {delay}s...",
                    severity="WARNING",
                    module="binance_ws",
                )
                await self._close_client()
                await asyncio.sleep(delay)
                await send_alert(
                    "WebSocket reconnecting...",
                    severity="INFO",
                    module="binance_ws",
                )


async def run_kline_ingestion() -> None:
    if not settings.ingestion_enabled:
        logger.info("ingestion_disabled")
        return
    service = KlineIngestionService()
    await service.run_forever()
