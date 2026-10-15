"""trainer one-off mode

Revision ID: c4e8a2d6f1b3
Revises: b7d3f1a9c2e4
Create Date: 2026-10-15 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4e8a2d6f1b3"
down_revision: str | None = "b7d3f1a9c2e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # У всех «разрешать»: запись без блока работает как раньше
    op.add_column(
        "trainers",
        sa.Column("one_off_mode", sa.String(length=16), nullable=False, server_default="allow"),
    )


def downgrade() -> None:
    op.drop_column("trainers", "one_off_mode")
