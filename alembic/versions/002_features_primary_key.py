"""Add primary keys for features upserts.

Revision ID: 002
Revises: 001
Create Date: 2026-05-18
"""

from typing import Sequence, Union

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint c
                JOIN pg_class t ON c.conrelid = t.oid
                WHERE t.relname = 'features' AND c.contype = 'p'
            ) THEN
                ALTER TABLE features
                ADD CONSTRAINT features_pkey PRIMARY KEY (time, symbol, timeframe);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE features DROP CONSTRAINT IF EXISTS features_pkey;")
