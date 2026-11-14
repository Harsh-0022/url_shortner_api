from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from url_shortener.models import Link


def get_link_by_code(db: Session, short_code: str) -> Link | None:
    statement = select(Link).where(Link.short_code == short_code)
    return db.scalar(statement)


def create_link(
    db: Session,
    *,
    short_code: str,
    target_url: str,
    expires_at: datetime | None = None,
) -> Link:
    link = Link(short_code=short_code, target_url=target_url, expires_at=expires_at)
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def increment_clicks(db: Session, short_code: str) -> None:
    statement = update(Link).where(Link.short_code == short_code).values(clicks=Link.clicks + 1)
    db.execute(statement)
    db.commit()
