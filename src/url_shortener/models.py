from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from url_shortener.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Link(Base):
    __tablename__ = "links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    short_code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, nullable=True
    )
