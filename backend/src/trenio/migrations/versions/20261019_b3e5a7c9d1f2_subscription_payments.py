"""subscription payments

Revision ID: b3e5a7c9d1f2
Revises: a2d4f6b8c0e1
Create Date: 2026-10-19 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b3e5a7c9d1f2"
down_revision: str | None = "a2d4f6b8c0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "subscription_payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trainer_id", sa.Integer(), nullable=False),
        sa.Column("plan", sa.String(length=16), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("balance_used", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("transaction_id", sa.String(length=64), nullable=True),
        sa.Column("redirect_url", sa.Text(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'paid', 'canceled')",
            name=op.f("ck_subscription_payments_status"),
        ),
        sa.CheckConstraint(
            "amount >= 0 AND balance_used >= 0", name=op.f("ck_subscription_payments_amounts")
        ),
        sa.ForeignKeyConstraint(
            ["trainer_id"],
            ["trainers.id"],
            name=op.f("fk_subscription_payments_trainer_id_trainers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscription_payments")),
        sa.UniqueConstraint("transaction_id", name=op.f("uq_subscription_payments_transaction_id")),
    )
    op.create_index(
        "ix_subscription_payments_pending",
        "subscription_payments",
        ["created_at"],
        unique=False,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        op.f("ix_subscription_payments_trainer_id"),
        "subscription_payments",
        ["trainer_id"],
        unique=False,
    )
    op.create_table(
        "balance_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trainer_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("payment_id", sa.Integer(), nullable=True),
        sa.Column("from_trainer_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('referral', 'payment', 'refund')", name=op.f("ck_balance_entries_kind")
        ),
        sa.ForeignKeyConstraint(
            ["from_trainer_id"],
            ["trainers.id"],
            name=op.f("fk_balance_entries_from_trainer_id_trainers"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["subscription_payments.id"],
            name=op.f("fk_balance_entries_payment_id_subscription_payments"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["trainer_id"],
            ["trainers.id"],
            name=op.f("fk_balance_entries_trainer_id_trainers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_balance_entries")),
    )
    op.create_index(
        op.f("ix_balance_entries_from_trainer_id"),
        "balance_entries",
        ["from_trainer_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_balance_entries_trainer_id"), "balance_entries", ["trainer_id"], unique=False
    )
    op.add_column(
        "trainers", sa.Column("balance", sa.Integer(), server_default=sa.text("0"), nullable=False)
    )


def downgrade() -> None:
    op.drop_column("trainers", "balance")
    op.drop_index(op.f("ix_balance_entries_trainer_id"), table_name="balance_entries")
    op.drop_index(op.f("ix_balance_entries_from_trainer_id"), table_name="balance_entries")
    op.drop_table("balance_entries")
    op.drop_index(op.f("ix_subscription_payments_trainer_id"), table_name="subscription_payments")
    op.drop_index(
        "ix_subscription_payments_pending",
        table_name="subscription_payments",
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.drop_table("subscription_payments")
