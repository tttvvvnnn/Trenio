"""user last seen

Revision ID: c3e7a9b1d4f2
Revises: 3c7a9e2f4b15
Create Date: 2026-10-14 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3e7a9b1d4f2"
down_revision: str | None = "3c7a9e2f4b15"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "last_seen_at")
