"""trainer reminders on by default

Revision ID: c4f6a8b0d2e4
Revises: b3e5a7c9d1f2
Create Date: 2026-10-19 11:00:00.000000

Напоминания тренеру теперь включены по умолчанию. Тем, кто настройки не сохранял (строки в
reminder_settings нет), ставим напоминание за час о будущих подтверждённых записях — раньше
они не ставились. Ключ тот же, что у schedule_reminders, поэтому дублей не будет.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c4f6a8b0d2e4"
down_revision: str | None = "b3e5a7c9d1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO notifications (user_id, kind, booking_id, payload, dedup_key, send_at)
        SELECT t.user_id, 'reminder', b.id, '{"role": "trainer", "offset": 60}'::jsonb,
               'reminder:' || b.id || ':trainer:60', b.starts_at - interval '60 minutes'
        FROM bookings b
        JOIN trainers t ON t.id = b.trainer_id
        WHERE b.status = 'confirmed'
          AND b.starts_at - interval '60 minutes' > now()
          AND NOT EXISTS (
              SELECT 1 FROM reminder_settings r
              WHERE r.user_id = t.user_id AND r.role = 'trainer'
          )
        ON CONFLICT (dedup_key) DO NOTHING
        """
    )


def downgrade() -> None:
    # Поставленные напоминания не трогаем: без строки настроек они и так соответствовали бы
    # новым значениям по умолчанию
    pass
