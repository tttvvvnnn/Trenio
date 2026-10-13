"""clients and bookings

Revision ID: ae4fc9a22225
Revises: 61d3ce433f6d
Create Date: 2026-10-13 11:10:06.114574
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ae4fc9a22225"
down_revision: str | None = "61d3ce433f6d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trainer_clients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trainer_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["trainer_id"],
            ["trainers.id"],
            name=op.f("fk_trainer_clients_trainer_id_trainers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_trainer_clients_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trainer_clients")),
        sa.UniqueConstraint("trainer_id", "user_id", name="uq_trainer_clients_pair"),
    )
    op.create_index(
        op.f("ix_trainer_clients_user_id"), "trainer_clients", ["user_id"], unique=False
    )
    op.create_table(
        "bookings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trainer_id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.String(length=16), nullable=False),
        sa.Column("cancelled_by", sa.String(length=16), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "cancelled_by IS NULL OR cancelled_by IN ('client', 'trainer')",
            name=op.f("ck_bookings_cancelled_by"),
        ),
        sa.CheckConstraint(
            "created_by IN ('client', 'trainer')", name=op.f("ck_bookings_created_by")
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'declined', 'cancelled')",
            name=op.f("ck_bookings_status"),
        ),
        sa.CheckConstraint("starts_at < ends_at", name=op.f("ck_bookings_time_order")),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["users.id"],
            name=op.f("fk_bookings_client_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            name=op.f("fk_bookings_service_id_services"),
        ),
        sa.ForeignKeyConstraint(
            ["trainer_id"],
            ["trainers.id"],
            name=op.f("fk_bookings_trainer_id_trainers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bookings")),
    )
    op.create_index(
        "ix_bookings_client_starts", "bookings", ["client_id", "starts_at"], unique=False
    )
    op.create_index(
        "ix_bookings_trainer_starts", "bookings", ["trainer_id", "starts_at"], unique=False
    )
    op.create_index(
        "uq_bookings_client_session",
        "bookings",
        ["client_id", "service_id", "starts_at"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'confirmed')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_bookings_client_session",
        table_name="bookings",
        postgresql_where=sa.text("status IN ('pending', 'confirmed')"),
    )
    op.drop_index("ix_bookings_trainer_starts", table_name="bookings")
    op.drop_index("ix_bookings_client_starts", table_name="bookings")
    op.drop_table("bookings")
    op.drop_index(op.f("ix_trainer_clients_user_id"), table_name="trainer_clients")
    op.drop_table("trainer_clients")
