"""trainer rules

Revision ID: 3c5e9b7d2f41
Revises: 7725d1070b35
Create Date: 2026-10-13 22:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3c5e9b7d2f41"
down_revision: str | None = "7725d1070b35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trainers", sa.Column("rules", sa.Text(), nullable=True))
    op.add_column(
        "trainers", sa.Column("rules_updated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "trainer_clients",
        sa.Column("rules_accepted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("trainer_clients", "rules_accepted_at")
    op.drop_column("trainers", "rules_updated_at")
    op.drop_column("trainers", "rules")
