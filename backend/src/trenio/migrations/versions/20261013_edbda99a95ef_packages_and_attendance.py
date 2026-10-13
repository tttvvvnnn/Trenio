"""packages and attendance

Revision ID: edbda99a95ef
Revises: a1830b5ccb1f
Create Date: 2026-10-13 16:47:02.970971
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "edbda99a95ef"
down_revision: str | None = "a1830b5ccb1f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "package_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trainer_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=True),
        sa.Column("sessions_count", sa.Integer(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("valid_days", sa.Integer(), nullable=True),
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
        sa.CheckConstraint("price >= 0", name=op.f("ck_package_templates_price")),
        sa.CheckConstraint(
            "sessions_count BETWEEN 1 AND 200", name=op.f("ck_package_templates_sessions_count")
        ),
        sa.CheckConstraint(
            "valid_days IS NULL OR valid_days >= 1", name=op.f("ck_package_templates_valid_days")
        ),
        sa.ForeignKeyConstraint(
            ["service_id"], ["services.id"], name=op.f("fk_package_templates_service_id_services")
        ),
        sa.ForeignKeyConstraint(
            ["trainer_id"],
            ["trainers.id"],
            name=op.f("fk_package_templates_trainer_id_trainers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_package_templates")),
    )
    op.create_index(
        op.f("ix_package_templates_trainer_id"), "package_templates", ["trainer_id"], unique=False
    )
    op.create_table(
        "packages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trainer_id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=True),
        sa.Column("sessions_count", sa.Integer(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("purchased_on", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("price >= 0", name=op.f("ck_packages_price")),
        sa.CheckConstraint(
            "sessions_count BETWEEN 1 AND 200", name=op.f("ck_packages_sessions_count")
        ),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["users.id"],
            name=op.f("fk_packages_client_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["service_id"], ["services.id"], name=op.f("fk_packages_service_id_services")
        ),
        sa.ForeignKeyConstraint(
            ["trainer_id"],
            ["trainers.id"],
            name=op.f("fk_packages_trainer_id_trainers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_packages")),
    )
    op.create_index("ix_packages_client", "packages", ["client_id"], unique=False)
    op.create_index(
        "ix_packages_trainer_client", "packages", ["trainer_id", "client_id"], unique=False
    )
    op.create_table(
        "package_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("package_id", sa.Integer(), nullable=False),
        sa.Column("booking_id", sa.Integer(), nullable=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
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
            "status IN ('attended', 'missed_charged')", name=op.f("ck_package_sessions_status")
        ),
        sa.ForeignKeyConstraint(
            ["booking_id"],
            ["bookings.id"],
            name=op.f("fk_package_sessions_booking_id_bookings"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["package_id"],
            ["packages.id"],
            name=op.f("fk_package_sessions_package_id_packages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_package_sessions")),
        sa.UniqueConstraint("booking_id", name=op.f("uq_package_sessions_booking_id")),
    )
    op.create_index(
        op.f("ix_package_sessions_package_id"), "package_sessions", ["package_id"], unique=False
    )
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("package_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=False),
        sa.Column("comment", sa.String(length=256), nullable=True),
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
        sa.CheckConstraint("amount > 0", name=op.f("ck_payments_amount")),
        sa.ForeignKeyConstraint(
            ["package_id"],
            ["packages.id"],
            name=op.f("fk_payments_package_id_packages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
    )
    op.create_index(op.f("ix_payments_package_id"), "payments", ["package_id"], unique=False)
    op.add_column("bookings", sa.Column("attendance", sa.String(length=16), nullable=True))
    op.add_column(
        "bookings", sa.Column("attendance_marked_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        op.f("ck_bookings_attendance"),
        "bookings",
        "attendance IS NULL OR attendance IN ('attended', 'missed_charged', 'missed_free')",
    )
    op.add_column("trainer_clients", sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("trainer_clients", "notes")
    op.drop_constraint(op.f("ck_bookings_attendance"), "bookings", type_="check")
    op.drop_column("bookings", "attendance_marked_at")
    op.drop_column("bookings", "attendance")
    op.drop_index(op.f("ix_payments_package_id"), table_name="payments")
    op.drop_table("payments")
    op.drop_index(op.f("ix_package_sessions_package_id"), table_name="package_sessions")
    op.drop_table("package_sessions")
    op.drop_index("ix_packages_trainer_client", table_name="packages")
    op.drop_index("ix_packages_client", table_name="packages")
    op.drop_table("packages")
    op.drop_index(op.f("ix_package_templates_trainer_id"), table_name="package_templates")
    op.drop_table("package_templates")
