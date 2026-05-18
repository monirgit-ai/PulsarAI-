"""Initial TimescaleDB schema for PulsarAI.

Revision ID: 001
Revises:
Create Date: 2026-05-18
"""

from typing import Sequence, Union

from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")

    op.execute("""
        CREATE TABLE IF NOT EXISTS candles (
            time        TIMESTAMPTZ NOT NULL,
            symbol      TEXT NOT NULL,
            timeframe   TEXT NOT NULL,
            open        DOUBLE PRECISION,
            high        DOUBLE PRECISION,
            low         DOUBLE PRECISION,
            close       DOUBLE PRECISION,
            volume      DOUBLE PRECISION,
            num_trades  INTEGER,
            PRIMARY KEY (time, symbol, timeframe)
        );
    """)
    op.execute("""
        SELECT create_hypertable('candles', 'time', if_not_exists => TRUE);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_candles_symbol_tf_time
        ON candles (symbol, timeframe, time DESC);
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS features (
            time        TIMESTAMPTZ NOT NULL,
            symbol      TEXT NOT NULL,
            timeframe   TEXT NOT NULL,
            features    JSONB,
            PRIMARY KEY (time, symbol, timeframe)
        );
    """)
    op.execute("""
        SELECT create_hypertable('features', 'time', if_not_exists => TRUE);
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            time        TIMESTAMPTZ NOT NULL,
            symbol      TEXT NOT NULL,
            signal_type TEXT,
            direction   TEXT,
            confidence  DOUBLE PRECISION,
            metadata    JSONB,
            PRIMARY KEY (time, symbol, signal_type)
        );
    """)
    op.execute("""
        SELECT create_hypertable('signals', 'time', if_not_exists => TRUE);
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            opened_at       TIMESTAMPTZ NOT NULL,
            closed_at       TIMESTAMPTZ,
            symbol          TEXT NOT NULL,
            side            TEXT NOT NULL,
            entry_price     DOUBLE PRECISION,
            exit_price      DOUBLE PRECISION,
            quantity        DOUBLE PRECISION,
            pnl_usdt        DOUBLE PRECISION,
            pnl_pct         DOUBLE PRECISION,
            fees_paid       DOUBLE PRECISION,
            stop_loss       DOUBLE PRECISION,
            take_profit     DOUBLE PRECISION,
            signals_used    JSONB,
            market_regime   TEXT,
            status          TEXT NOT NULL DEFAULT 'OPEN'
        );
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_trades_symbol_opened
        ON trades (symbol, opened_at DESC);
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS sentiment (
            time        TIMESTAMPTZ NOT NULL,
            symbol      TEXT NOT NULL,
            source      TEXT NOT NULL,
            score       DOUBLE PRECISION,
            raw_text    TEXT,
            metadata    JSONB,
            PRIMARY KEY (time, symbol, source)
        );
    """)
    op.execute("""
        SELECT create_hypertable('sentiment', 'time', if_not_exists => TRUE);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sentiment CASCADE;")
    op.execute("DROP TABLE IF EXISTS trades CASCADE;")
    op.execute("DROP TABLE IF EXISTS signals CASCADE;")
    op.execute("DROP TABLE IF EXISTS features CASCADE;")
    op.execute("DROP TABLE IF EXISTS candles CASCADE;")
