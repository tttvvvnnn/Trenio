"""trainer slot step

Revision ID: a1830b5ccb1f
Revises: ae4fc9a22225
Create Date: 2026-10-13 11:58:11.078969
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1830b5ccb1f"
down_revision: str | None = "ae4fc9a22225"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Существующие тренеры тоже получают шаг 15 минут вместо сетки по длительности услуги
    op.add_column(
        "trainers",
        sa.Column("slot_step_min", sa.Integer(), server_default=sa.text("15"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_trainers_slot_step"), "trainers", "slot_step_min IN (0, 5, 10, 15, 20, 30, 60)"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_trainers_slot_step"), "trainers", type_="check")
    op.drop_column("trainers", "slot_step_min")
