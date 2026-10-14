"""booking comments and reschedule

Revision ID: 5b2e8c1d9f37
Revises: 3c5e9b7d2f41
Create Date: 2026-10-14 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5b2e8c1d9f37"
down_revision: str | None = "3c5e9b7d2f41"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("cancel_comment", sa.Text(), nullable=True))
    op.add_column(
        "bookings", sa.Column("rescheduled_from", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("bookings", sa.Column("rescheduled_by", sa.String(length=16), nullable=True))
    op.add_column(
        "bookings", sa.Column("rescheduled_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("bookings", sa.Column("reschedule_comment", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_bookings_rescheduled_by"),
        "bookings",
        "rescheduled_by IS NULL OR rescheduled_by IN ('client', 'trainer')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_bookings_rescheduled_by"), "bookings", type_="check")
    op.drop_column("bookings", "reschedule_comment")
    op.drop_column("bookings", "rescheduled_at")
    op.drop_column("bookings", "rescheduled_by")
    op.drop_column("bookings", "rescheduled_from")
    op.drop_column("bookings", "cancel_comment")
