"""bots

Revision ID: a94c0a7d3176
Revises: c4f6a8b0d2e4
Create Date: 2026-10-20 19:00:00.000000

Таблица ботов с одной строкой — основным ботом (id 1). Его id и имя в Telegram приложение
заполняет при старте, токен остаётся в BOT_TOKEN. Всем тренерам, приглашениям, оплатам и
ошибкам Mini App ставится основной бот: до своих ботов специалистов всё живёт в нём.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a94c0a7d3176"
down_revision: str | None = "c4f6a8b0d2e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MAIN_BOT_ID = 1
# Таблица и можно ли bot_id быть пустым
_LINKED = (
    ("trainers", False),
    ("trainer_invites", False),
    ("subscription_payments", False),
    ("client_errors", True),
)


def upgrade() -> None:
    op.create_table(
        "bots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(16), server_default="telegram", nullable=False),
        sa.Column("external_id", sa.BigInteger(), nullable=True),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("token_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("slug", sa.String(32), nullable=False),
        sa.Column("vertical", sa.String(16), server_default="fitness", nullable=False),
        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("is_main", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("paid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("platform IN ('telegram')", name=op.f("ck_bots_platform")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bots")),
        sa.UniqueConstraint("platform", "external_id", name="uq_bots_platform_external_id"),
        sa.UniqueConstraint("slug", name=op.f("uq_bots_slug")),
    )
    op.create_index(
        "uq_bots_main", "bots", ["is_main"], unique=True, postgresql_where=sa.text("is_main")
    )
    op.execute(f"INSERT INTO bots (id, slug, is_main) VALUES ({MAIN_BOT_ID}, 'main', true)")
    # Следующий бот получит id 2, а не упрётся в занятый 1
    op.execute("SELECT setval(pg_get_serial_sequence('bots', 'id'), (SELECT max(id) FROM bots))")

    for table, nullable in _LINKED:
        op.add_column(table, sa.Column("bot_id", sa.Integer(), nullable=True))
        op.execute(f"UPDATE {table} SET bot_id = {MAIN_BOT_ID}")
        if not nullable:
            op.alter_column(table, "bot_id", nullable=False)
        op.create_foreign_key(
            op.f(f"fk_{table}_bot_id_bots"), table, "bots", ["bot_id"], ["id"], ondelete="RESTRICT"
        )
        op.create_index(op.f(f"ix_{table}_bot_id"), table, ["bot_id"])


def downgrade() -> None:
    for table, _ in reversed(_LINKED):
        op.drop_index(op.f(f"ix_{table}_bot_id"), table_name=table)
        op.drop_constraint(op.f(f"fk_{table}_bot_id_bots"), table, type_="foreignkey")
        op.drop_column(table, "bot_id")
    op.drop_index("uq_bots_main", table_name="bots")
    op.drop_table("bots")
