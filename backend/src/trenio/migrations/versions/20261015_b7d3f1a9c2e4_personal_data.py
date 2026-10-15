"""personal data: consent, deleted accounts, client phone

Revision ID: b7d3f1a9c2e4
Revises: 9a1c5e7b3d28
Create Date: 2026-10-15 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7d3f1a9c2e4"
down_revision: str | None = "9a1c5e7b3d28"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Пустые у всех: согласие спросим и у тех, кто уже пользуется приложением
    op.add_column("users", sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("consent_version", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("trainer_clients", sa.Column("phone", sa.String(length=32), nullable=True))
    op.add_column(
        "trainer_clients",
        sa.Column("phone_consent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("trainer_clients", "phone_consent_at")
    op.drop_column("trainer_clients", "phone")
    op.drop_column("users", "deleted_at")
    op.drop_column("users", "consent_version")
    op.drop_column("users", "consent_at")
