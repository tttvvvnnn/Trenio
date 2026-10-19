"""trainer referrals

Revision ID: f1c3e5a7b9d2
Revises: f1b5d3a7c9e2
Create Date: 2026-10-19 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f1c3e5a7b9d2"
down_revision: str | None = "f1b5d3a7c9e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trainers", sa.Column("referral_code", sa.String(length=32), nullable=True))
    # Уже существующим тренерам — случайный код из 22 символов, как у новых
    op.execute(
        "UPDATE trainers SET referral_code = "
        "substr(md5(random()::text || id::text || clock_timestamp()::text), 1, 22)"
    )
    op.alter_column("trainers", "referral_code", nullable=False)
    op.create_unique_constraint(op.f("uq_trainers_referral_code"), "trainers", ["referral_code"])
    op.add_column("trainers", sa.Column("referred_by_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_trainers_referred_by_id_trainers"),
        "trainers",
        "trainers",
        ["referred_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_trainers_referred_by_id"), "trainers", ["referred_by_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_trainers_referred_by_id"), table_name="trainers")
    op.drop_constraint(op.f("fk_trainers_referred_by_id_trainers"), "trainers", type_="foreignkey")
    op.drop_column("trainers", "referred_by_id")
    op.drop_constraint(op.f("uq_trainers_referral_code"), "trainers", type_="unique")
    op.drop_column("trainers", "referral_code")
