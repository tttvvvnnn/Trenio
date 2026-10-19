"""trainer subscription

Revision ID: a2d4f6b8c0e1
Revises: f1c3e5a7b9d2
Create Date: 2026-10-19 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a2d4f6b8c0e1"
down_revision: str | None = "f1c3e5a7b9d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trainers", sa.Column("trial_until", sa.DateTime(timezone=True)))
    op.add_column("trainers", sa.Column("pro_until", sa.DateTime(timezone=True)))
    # Тем, кто уже пользуется Trenio, — такие же 30 дней пробного периода, как новым
    op.execute("UPDATE trainers SET trial_until = now() + interval '30 days'")


def downgrade() -> None:
    op.drop_column("trainers", "pro_until")
    op.drop_column("trainers", "trial_until")
