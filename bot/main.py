"""PulsarAI bot entrypoint — Phase 1: health loop + Telegram startup alert."""

from __future__ import annotations

import asyncio
import signal

import structlog

from config.logging_config import configure_logging
from config.settings import settings
from data.storage import redis_cache, timescale
from monitoring.health_check import run_health_check
from monitoring.telegram_bot import notify_startup, send_alert

logger = structlog.get_logger(__name__)

_shutdown = asyncio.Event()


def _handle_signal() -> None:
    logger.info("shutdown_signal_received")
    _shutdown.set()


async def health_loop() -> None:
    interval = settings.bot_health_interval_seconds
    while not _shutdown.is_set():
        try:
            status = await run_health_check()
            if not status.healthy:
                await send_alert(
                    f"Health check failed.\n{status.details}",
                    severity="WARNING",
                    module="health_check",
                )
            else:
                logger.info("health_ok", details=status.details)
        except Exception:
            logger.exception("health_loop_error")

        try:
            await asyncio.wait_for(_shutdown.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue


async def run() -> None:
    configure_logging(settings.log_level)
    logger.info(
        "bot_starting",
        environment=settings.environment,
        paper_trading=settings.paper_trading,
    )

    await notify_startup(settings.environment, settings.paper_trading)

    # Verify connectivity
    status = await run_health_check()
    if status.healthy:
        await send_alert(
            "Database and Redis connected.",
            severity="INFO",
            module="bot",
        )
    else:
        await send_alert(
            f"Startup health check degraded: {status.details}",
            severity="WARNING",
            module="bot",
        )

    await health_loop()


async def main() -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            # Windows
            pass

    try:
        await run()
    finally:
        await send_alert("PulsarAI shutting down.", severity="INFO", module="bot")
        await timescale.close_pool()
        await redis_cache.close_redis()
        logger.info("bot_stopped")


if __name__ == "__main__":
    asyncio.run(main())
