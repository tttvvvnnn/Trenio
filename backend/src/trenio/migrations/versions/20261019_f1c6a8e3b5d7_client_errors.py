"""client errors

Revision ID: f1c6a8e3b5d7
Revises: e3a7c5f9b2d8
Create Date: 2026-10-19 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f1c6a8e3b5d7"
down_revision: str | None = "e3a7c5f9b2d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "client_errors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("screen", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_client_errors_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_client_errors")),
    )
    op.create_index(op.f("ix_client_errors_created_at"), "client_errors", ["created_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_client_errors_created_at"), table_name="client_errors")
    op.drop_table("client_errors")
