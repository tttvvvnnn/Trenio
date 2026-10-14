"""user avatars

Revision ID: 8d4f1a6c2b90
Revises: 5b2e8c1d9f37
Create Date: 2026-10-14 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8d4f1a6c2b90"
down_revision: str | None = "5b2e8c1d9f37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("avatar_mode", sa.String(length=16), server_default="telegram", nullable=False),
    )
    op.add_column("users", sa.Column("avatar_key", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("avatar_telegram_id", sa.String(length=64), nullable=True))
    op.add_column(
        "users", sa.Column("avatar_checked_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_unique_constraint(op.f("uq_users_avatar_key"), "users", ["avatar_key"])
    op.create_check_constraint(
        op.f("ck_users_avatar_mode"),
        "users",
        "avatar_mode IN ('telegram', 'custom', 'none')",
    )
    op.create_table(
        "user_avatars",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_avatars_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_avatars")),
    )


def downgrade() -> None:
    op.drop_table("user_avatars")
    op.drop_constraint(op.f("ck_users_avatar_mode"), "users", type_="check")
    op.drop_constraint(op.f("uq_users_avatar_key"), "users", type_="unique")
    op.drop_column("users", "avatar_checked_at")
    op.drop_column("users", "avatar_telegram_id")
    op.drop_column("users", "avatar_key")
    op.drop_column("users", "avatar_mode")
