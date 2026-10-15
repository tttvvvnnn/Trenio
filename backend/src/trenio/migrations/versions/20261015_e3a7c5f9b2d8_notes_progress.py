"""session notes and client measurements

Revision ID: e3a7c5f9b2d8
Revises: d9f2b6a4e8c1
Create Date: 2026-10-15 19:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e3a7c5f9b2d8"
down_revision: str | None = "d9f2b6a4e8c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("trainer_note", sa.Text(), nullable=True))
    op.add_column(
        "bookings",
        sa.Column(
            "trainer_note_private", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.create_table(
        "client_measurements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trainer_client_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("label", sa.String(length=48), nullable=True),
        sa.Column("unit", sa.String(length=16), nullable=True),
        sa.Column("value", sa.Numeric(8, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("value > 0", name=op.f("ck_client_measurements_value")),
        sa.ForeignKeyConstraint(
            ["trainer_client_id"],
            ["trainer_clients.id"],
            name=op.f("fk_client_measurements_trainer_client_id_trainer_clients"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_client_measurements")),
    )
    op.create_index(
        "ix_client_measurements_link_day",
        "client_measurements",
        ["trainer_client_id", "day"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_client_measurements_link_day", "client_measurements")
    op.drop_table("client_measurements")
    op.drop_column("bookings", "trainer_note_private")
    op.drop_column("bookings", "trainer_note")
