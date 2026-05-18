"""Background monitoring scheduler — metrics, drift, daily summary."""

from __future__ import annotations

import asyncio
import signal

import structlog

from config.logging_config import configure_logging
from config.settings import settings
from data.storage import redis_cache, timescale
from monitoring.daily_summary import DailySummaryService
from monitoring.drift_detector import DriftDetector
from monitoring.extended_health import run_extended_health_check
from monitoring.performance_tracker import PerformanceTracker
from monitoring.telegram_alerts import notify_system_error
from monitoring.telegram_bot import notify_startup, send_alert

logger = structlog.get_logger(__name__)

_shutdown = asyncio.Event()


def _handle_signal() -> None:
    _shutdown.set()


async def metrics_loop() -> None:
    tracker = PerformanceTracker()
    interval = settings.metrics_interval_seconds
    while not _shutdown.is_set():
        try:
            await tracker.collect()
        except Exception as exc:
            logger.exception("metrics_loop_error")
            await notify_system_error("scheduler", "Metrics collection failed", exc=exc)
        try:
            await asyncio.wait_for(_shutdown.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue


async def health_loop() -> None:
    interval = settings.bot_health_interval_seconds
    while not _shutdown.is_set():
        try:
            status = await run_extended_health_check()
            if not status.healthy:
                await send_alert(
                    f"Extended health check failed.\n{status.details}",
                    severity="WARNING",
                    module="extended_health",
                )
        except Exception as exc:
            logger.exception("health_loop_error")
            await notify_system_error("scheduler", "Health check failed", exc=exc)
        try:
            await asyncio.wait_for(_shutdown.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue


async def drift_loop() -> None:
    detector = DriftDetector()
    interval_hours = settings.drift_check_interval_hours
    while not _shutdown.is_set():
        try:
            await detector.check_signal_drift()
        except Exception as exc:
            logger.exception("drift_loop_error")
        try:
            await asyncio.wait_for(_shutdown.wait(), timeout=interval_hours * 3600)
        except asyncio.TimeoutError:
            continue


async def daily_summary_loop() -> None:
    service = DailySummaryService()
    while not _shutdown.is_set():
        try:
            await service.maybe_send()
        except Exception as exc:
            logger.exception("daily_summary_error")
        try:
            await asyncio.wait_for(_shutdown.wait(), timeout=300)
        except asyncio.TimeoutError:
            continue


async def run() -> None:
    configure_logging(settings.log_level)
    logger.info("scheduler_starting", environment=settings.environment)
    await notify_startup(settings.environment, settings.paper_trading)

    tasks = [
        asyncio.create_task(metrics_loop(), name="metrics"),
        asyncio.create_task(health_loop(), name="health"),
        asyncio.create_task(drift_loop(), name="drift"),
        asyncio.create_task(daily_summary_loop(), name="daily_summary"),
    ]
    await asyncio.gather(*tasks, return_exceptions=True)


async def main() -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            pass
    try:
        await run()
    finally:
        _shutdown.set()
        await timescale.close_pool()
        await redis_cache.close_redis()
        logger.info("scheduler_stopped")


if __name__ == "__main__":
    asyncio.run(main())
