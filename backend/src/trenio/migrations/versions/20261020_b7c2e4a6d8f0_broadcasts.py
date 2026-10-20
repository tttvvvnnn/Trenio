"""broadcasts

Revision ID: b7c2e4a6d8f0
Revises: f6385e52f1a5
Create Date: 2026-10-20 21:00:00.000000

Рассылки тренерам из веб-админки. Сообщения уходят через очередь notifications.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7c2e4a6d8f0"
down_revision: str | None = "f6385e52f1a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "broadcasts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bot_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("segment", sa.String(32), nullable=False),
        sa.Column("with_button", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("recipients", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["bot_id"], ["bots.id"], name=op.f("fk_broadcasts_bot_id_bots"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_broadcasts")),
    )
    op.create_index(op.f("ix_broadcasts_bot_id"), "broadcasts", ["bot_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_broadcasts_bot_id"), table_name="broadcasts")
    op.drop_table("broadcasts")
