"""Prometheus metrics for PulsarAI."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, generate_latest

# Portfolio
EQUITY_USDT = Gauge("pulsarai_equity_usdt", "Total portfolio equity in USDT")
CASH_USDT = Gauge("pulsarai_cash_usdt", "Available USDT cash")
DAILY_PNL_USDT = Gauge("pulsarai_daily_pnl_usdt", "Daily realized PnL in USDT")
OPEN_POSITIONS = Gauge("pulsarai_open_positions", "Number of open positions")
CIRCUIT_BREAKER_ACTIVE = Gauge("pulsarai_circuit_breaker_active", "1 if circuit breaker is active")

# Trading
TRADES_TOTAL = Counter("pulsarai_trades_total", "Total trades executed", ["side", "mode"])
WIN_RATE_30D = Gauge("pulsarai_win_rate_30d", "Win rate over last 30 days")
SHARPE_30D = Gauge("pulsarai_sharpe_30d", "Sharpe ratio over last 30 days")
MAX_DRAWDOWN_PCT = Gauge("pulsarai_max_drawdown_pct", "Max drawdown current period %")
FEES_PAID_DAILY = Gauge("pulsarai_fees_paid_daily_usdt", "Fees paid today in USDT")

# Infrastructure
WS_CONNECTED = Gauge("pulsarai_ws_connected", "1 if WebSocket ingestion is connected")
DB_LATENCY_MS = Gauge("pulsarai_db_latency_ms", "Database ping latency in milliseconds")
REDIS_CONNECTED = Gauge("pulsarai_redis_connected", "1 if Redis is connected")
CANDLES_IN_DB = Gauge("pulsarai_candles_in_db", "Total candles stored")

# ML / signals
MODEL_CONFIDENCE = Gauge("pulsarai_model_confidence", "Latest ensemble confidence", ["symbol"])
DRIFT_SCORE = Gauge("pulsarai_drift_score", "Feature drift score 0-1")

INFERENCE_LATENCY = Histogram(
    "pulsarai_inference_latency_seconds",
    "Model inference latency",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)


def metrics_payload() -> bytes:
    return generate_latest()
