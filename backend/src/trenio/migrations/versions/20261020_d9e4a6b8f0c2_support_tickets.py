"""support tickets

Revision ID: d9e4a6b8f0c2
Revises: c8d3f5a7e9b1
Create Date: 2026-10-20 23:00:00.000000

Обращения и отзывы тренеров из Mini App.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d9e4a6b8f0c2"
down_revision: str | None = "c8d3f5a7e9b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "support_tickets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bot_id", sa.Integer(), nullable=False),
        sa.Column("trainer_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="new", nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('question', 'problem', 'idea', 'review')",
            name=op.f("ck_support_tickets_kind"),
        ),
        sa.CheckConstraint(
            "status IN ('new', 'answered', 'closed')", name=op.f("ck_support_tickets_status")
        ),
        sa.CheckConstraint(
            "rating IS NULL OR rating BETWEEN 1 AND 5", name=op.f("ck_support_tickets_rating")
        ),
        sa.ForeignKeyConstraint(
            ["bot_id"],
            ["bots.id"],
            name=op.f("fk_support_tickets_bot_id_bots"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["trainer_id"],
            ["trainers.id"],
            name=op.f("fk_support_tickets_trainer_id_trainers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_tickets")),
    )
    op.create_index(op.f("ix_support_tickets_bot_id"), "support_tickets", ["bot_id"], unique=False)
    op.create_index(
        op.f("ix_support_tickets_trainer_id"), "support_tickets", ["trainer_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_support_tickets_trainer_id"), table_name="support_tickets")
    op.drop_index(op.f("ix_support_tickets_bot_id"), table_name="support_tickets")
    op.drop_table("support_tickets")
