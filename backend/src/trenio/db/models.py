"""Модели таблиц. На этапе 2 только пользователи, остальное добавляется по этапам."""

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from trenio.db.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    # Внутренний id; telegram_id лишь один из способов входа (потом появятся телефон и т.п.)
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    first_name: Mapped[str] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    username: Mapped[str | None] = mapped_column(String(64))
    language_code: Mapped[str | None] = mapped_column(String(16))
