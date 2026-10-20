"""promo codes

Revision ID: c8d3f5a7e9b1
Revises: b7c2e4a6d8f0
Create Date: 2026-10-20 21:30:00.000000

Промокоды тренеров: скидка на одну оплату Pro или дни Pro без оплаты.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8d3f5a7e9b1"
down_revision: str | None = "b7c2e4a6d8f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "promo_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bot_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('percent', 'rubles', 'days')", name=op.f("ck_promo_codes_kind")
        ),
        sa.CheckConstraint(
            "max_uses IS NULL OR max_uses > 0", name=op.f("ck_promo_codes_max_uses")
        ),
        sa.CheckConstraint("value > 0", name=op.f("ck_promo_codes_value")),
        sa.ForeignKeyConstraint(
            ["bot_id"], ["bots.id"], name=op.f("fk_promo_codes_bot_id_bots"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_promo_codes")),
        sa.UniqueConstraint("code", name=op.f("uq_promo_codes_code")),
    )
    op.create_index(op.f("ix_promo_codes_bot_id"), "promo_codes", ["bot_id"], unique=False)
    op.create_table(
        "promo_redemptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code_id", sa.Integer(), nullable=False),
        sa.Column("trainer_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("payment_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('reserved', 'used')", name=op.f("ck_promo_redemptions_status")
        ),
        sa.ForeignKeyConstraint(
            ["code_id"],
            ["promo_codes.id"],
            name=op.f("fk_promo_redemptions_code_id_promo_codes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["subscription_payments.id"],
            name=op.f("fk_promo_redemptions_payment_id_subscription_payments"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["trainer_id"],
            ["trainers.id"],
            name=op.f("fk_promo_redemptions_trainer_id_trainers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_promo_redemptions")),
        sa.UniqueConstraint("code_id", "trainer_id", name="uq_promo_redemptions_pair"),
    )
    op.create_index(
        op.f("ix_promo_redemptions_trainer_id"), "promo_redemptions", ["trainer_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_promo_redemptions_trainer_id"), table_name="promo_redemptions")
    op.drop_table("promo_redemptions")
    op.drop_index(op.f("ix_promo_codes_bot_id"), table_name="promo_codes")
    op.drop_table("promo_codes")
