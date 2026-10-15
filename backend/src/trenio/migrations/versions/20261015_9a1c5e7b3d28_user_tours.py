"""user tours

Revision ID: 9a1c5e7b3d28
Revises: 9a1c5e3b7d20
Create Date: 2026-10-15 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9a1c5e7b3d28"
down_revision: str | None = "9a1c5e3b7d20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Пустые у всех: вводный тур увидят и те, кто уже пользуется приложением
    op.add_column("users", sa.Column("trainer_tour_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("client_tour_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "client_tour_at")
    op.drop_column("users", "trainer_tour_at")
