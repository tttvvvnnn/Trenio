"""user custom name

Revision ID: 3c7a9e2f4b15
Revises: 8d4f1a6c2b90
Create Date: 2026-10-14 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3c7a9e2f4b15"
down_revision: str | None = "8d4f1a6c2b90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("name_custom", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("users", sa.Column("telegram_first_name", sa.String(length=128), nullable=True))
    op.add_column("users", sa.Column("telegram_last_name", sa.String(length=128), nullable=True))
    # Пока своих имён нет, нынешнее имя и есть имя из Telegram
    op.execute("UPDATE users SET telegram_first_name = first_name, telegram_last_name = last_name")


def downgrade() -> None:
    op.drop_column("users", "telegram_last_name")
    op.drop_column("users", "telegram_first_name")
    op.drop_column("users", "name_custom")
