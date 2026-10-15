"""booking terms: own price and no_package

Revision ID: 9a1c5e3b7d20
Revises: 4f8b2d6e1a73
Create Date: 2026-10-15 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9a1c5e3b7d20"
down_revision: str | None = "4f8b2d6e1a73"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("price", sa.Integer(), nullable=True))
    op.add_column(
        "bookings",
        sa.Column("no_package", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_check_constraint(op.f("ck_bookings_price"), "bookings", "price IS NULL OR price >= 0")
    # Цена разового занятия раньше бралась из услуги на лету: фиксируем её у старых записей
    op.execute(
        "UPDATE bookings SET price = services.price FROM services "
        "WHERE services.id = bookings.service_id"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_bookings_price"), "bookings", type_="check")
    op.drop_column("bookings", "no_package")
    op.drop_column("bookings", "price")
