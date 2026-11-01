"""balance top-up

Revision ID: e7a9c1b3d5f8
Revises: d9e4a6b8f0c2
Create Date: 2026-11-01 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e7a9c1b3d5f8"
down_revision: str | None = "d9e4a6b8f0c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_balance_entries_kind"), "balance_entries", type_="check")
    op.create_check_constraint(
        op.f("ck_balance_entries_kind"),
        "balance_entries",
        "kind IN ('referral', 'topup', 'payment', 'refund')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_balance_entries_kind"), "balance_entries", type_="check")
    op.create_check_constraint(
        op.f("ck_balance_entries_kind"),
        "balance_entries",
        "kind IN ('referral', 'payment', 'refund')",
    )
