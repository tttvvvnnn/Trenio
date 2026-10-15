"""offline clients

Revision ID: 4f8b2d6e1a73
Revises: c3e7a9b1d4f2
Create Date: 2026-10-15 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4f8b2d6e1a73"
down_revision: str | None = "c3e7a9b1d4f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("created_by_trainer_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_users_created_by_trainer_id_trainers",
        "users",
        "trainers",
        ["created_by_trainer_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("trainer_clients", sa.Column("claim_code", sa.String(32), nullable=True))
    op.create_unique_constraint("uq_trainer_clients_claim_code", "trainer_clients", ["claim_code"])


def downgrade() -> None:
    op.drop_constraint("uq_trainer_clients_claim_code", "trainer_clients", type_="unique")
    op.drop_column("trainer_clients", "claim_code")
    op.drop_constraint("fk_users_created_by_trainer_id_trainers", "users", type_="foreignkey")
    op.drop_column("users", "created_by_trainer_id")
