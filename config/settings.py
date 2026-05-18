"""Application settings loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_nested_delimiter="__",
    )

    environment: Literal["development", "staging", "production"] = "development"
    paper_trading: bool = True

    api_port: int = 18888
    postgres_port: int = 15432
    redis_port: int = 16379
    grafana_port: int = 13000
    prometheus_port: int = 19090

    binance_api_key: str = ""
    binance_api_secret: str = ""
    binance_testnet: bool = False

    database_url: str = "postgresql://pulsarai:pulsarai_dev@localhost:15432/pulsarai"
    redis_url: str = "redis://localhost:16379/0"

    postgres_user: str = "pulsarai"
    postgres_password: str = "pulsarai_dev"
    postgres_db: str = "pulsarai"

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_alerts_enabled: bool = False

    max_position_risk_pct: float = 0.02
    max_open_positions: int = 5
    max_single_asset_pct: float = 0.20
    max_daily_drawdown_pct: float = 0.05
    max_weekly_drawdown_pct: float = 0.10
    usdt_reserve_pct: float = 0.20
    min_trade_size_usdt: float = 50.0

    initial_budget_usdt: float = 1000.0

    cryptopanic_api_key: str = ""
    glassnode_api_key: str = ""

    log_level: str = "INFO"
    bot_health_interval_seconds: int = 60

    # Data ingestion
    ingestion_enabled: bool = True
    trading_symbols: str = "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT"
    ws_kline_intervals: str = "1m,1h"
    historical_intervals: str = "1h,4h,1d"
    historical_days: int = 90
    top_pairs_count: int = 10
    binance_rest_delay_seconds: float = 0.2

    @property
    def ws_kline_interval_list(self) -> list[str]:
        return [x.strip() for x in self.ws_kline_intervals.split(",") if x.strip()]

    @property
    def historical_interval_list(self) -> list[str]:
        return [x.strip() for x in self.historical_intervals.split(",") if x.strip()]

    @property
    def trading_symbol_list(self) -> list[str]:
        return [x.strip().upper() for x in self.trading_symbols.split(",") if x.strip()]

    @field_validator("telegram_chat_id", mode="before")
    @classmethod
    def strip_chat_id(cls, v: object) -> str:
        if v is None:
            return ""
        return str(v).strip()

    @property
    def telegram_configured(self) -> bool:
        return bool(
            self.telegram_alerts_enabled
            and self.telegram_bot_token
            and self.telegram_chat_id
        )

    @property
    def asyncpg_dsn(self) -> str:
        """DSN for asyncpg (strip +asyncpg suffix if present)."""
        url = self.database_url
        if url.startswith("postgresql+asyncpg://"):
            return url.replace("postgresql+asyncpg://", "postgresql://", 1)
        if url.startswith("postgresql+psycopg2://"):
            return url.replace("postgresql+psycopg2://", "postgresql://", 1)
        return url

    @property
    def sqlalchemy_url(self) -> str:
        """Sync URL for Alembic."""
        url = self.asyncpg_dsn
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
