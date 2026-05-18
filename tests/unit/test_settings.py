from config.settings import Settings


def test_defaults_use_unusual_ports() -> None:
    s = Settings(
        _env_file=None,
        binance_api_key="",
        binance_api_secret="",
    )
    assert s.api_port == 18888
    assert s.postgres_port == 15432
    assert s.redis_port == 16379
    assert s.grafana_port == 13000
    assert s.paper_trading is True


def test_telegram_configured_requires_all_fields() -> None:
    s = Settings(
        _env_file=None,
        telegram_alerts_enabled=True,
        telegram_bot_token="token",
        telegram_chat_id="123",
    )
    assert s.telegram_configured is True

    s2 = Settings(_env_file=None, telegram_alerts_enabled=True, telegram_bot_token="")
    assert s2.telegram_configured is False


def test_asyncpg_dsn_strips_driver_suffix() -> None:
    s = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://u:p@localhost:15432/pulsarai",
    )
    assert s.asyncpg_dsn == "postgresql://u:p@localhost:15432/pulsarai"
