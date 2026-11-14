import secrets
import string
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from valkey import Valkey

from url_shortener import cache, repository
from url_shortener.config import Settings
from url_shortener.models import Link
from url_shortener.schemas import LinkCreateRequest

BASE62_ALPHABET = string.ascii_letters + string.digits


class DomainError(Exception):
    """Base exception for business rule violations."""


class RedirectLoopError(DomainError):
    """Raised when target URL points back to the shortener host."""


class AliasConflictError(DomainError):
    """Raised when a requested custom alias already exists."""


class CodeGenerationError(DomainError):
    """Raised when unique code generation exceeds max retries."""


class LinkNotFoundError(DomainError):
    """Raised when a short code does not exist."""


class LinkExpiredError(DomainError):
    """Raised when a link has passed its TTL."""


class RateLimitExceededError(DomainError):
    """Raised when a client exceeds link creation rate limits."""


def generate_base62_code(length: int) -> str:
    return "".join(secrets.choice(BASE62_ALPHABET) for _ in range(length))


def is_link_expired(link: Link, now: datetime | None = None) -> bool:
    if link.expires_at is None:
        return False
    current_time = now or datetime.now(timezone.utc)
    expires_at = (
        link.expires_at.replace(tzinfo=timezone.utc)
        if link.expires_at.tzinfo is None
        else link.expires_at
    )
    return current_time >= expires_at


def _compute_cache_ttl(link: Link, default_ttl: int) -> int:
    if link.expires_at is None:
        return default_ttl
    expires_at = (
        link.expires_at.replace(tzinfo=timezone.utc)
        if link.expires_at.tzinfo is None
        else link.expires_at
    )
    remaining = int((expires_at - datetime.now(timezone.utc)).total_seconds())
    return max(0, min(default_ttl, remaining))


def create_short_link(
    db: Session,
    valkey_client: Valkey,
    payload: LinkCreateRequest,
    settings: Settings,
    client_ip: str,
) -> Link:
    if cache.is_rate_limited(
        valkey_client,
        client_ip=client_ip,
        max_requests=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
    ):
        raise RateLimitExceededError("Too many link creation requests. Please try again later.")

    target_str = str(payload.target_url)

    target_host = urlparse(target_str).netloc.lower()
    base_host = urlparse(settings.base_url).netloc.lower()
    if target_host == base_host:
        raise RedirectLoopError("Target URL cannot point to the shortener domain itself.")

    expires_at: datetime | None = None
    if payload.expires_in_hours is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=payload.expires_in_hours)

    if payload.custom_alias is not None:
        try:
            link = repository.create_link(
                db,
                short_code=payload.custom_alias,
                target_url=target_str,
                expires_at=expires_at,
            )
            ttl = _compute_cache_ttl(link, settings.cache_ttl_seconds)
            cache.set_cached_target(valkey_client, link.short_code, link.target_url, ttl)
            return link
        except IntegrityError as exc:
            db.rollback()
            raise AliasConflictError(
                f"Custom alias '{payload.custom_alias}' is already in use."
            ) from exc

    for _ in range(settings.max_collision_retries):
        candidate_code = generate_base62_code(settings.short_code_length)
        try:
            link = repository.create_link(
                db,
                short_code=candidate_code,
                target_url=target_str,
                expires_at=expires_at,
            )
            ttl = _compute_cache_ttl(link, settings.cache_ttl_seconds)
            cache.set_cached_target(valkey_client, link.short_code, link.target_url, ttl)
            return link
        except IntegrityError:
            db.rollback()
            continue

    raise CodeGenerationError("Failed to generate a unique short code after maximum retries.")


def resolve_redirect_target(
    db: Session,
    valkey_client: Valkey,
    short_code: str,
    settings: Settings,
) -> str:
    # Fast path: Valkey cache hit
    cached_url = cache.get_cached_target(valkey_client, short_code)
    if cached_url is not None:
        repository.increment_clicks(db, short_code)
        return cached_url

    # Slow path: Cache miss -> query SQLite and populate Valkey
    link = repository.get_link_by_code(db, short_code)
    if link is None:
        raise LinkNotFoundError(f"Short code '{short_code}' not found.")
    if is_link_expired(link):
        raise LinkExpiredError(f"Short code '{short_code}' has expired.")

    ttl = _compute_cache_ttl(link, settings.cache_ttl_seconds)
    cache.set_cached_target(valkey_client, link.short_code, link.target_url, ttl)

    repository.increment_clicks(db, short_code)
    return link.target_url


def get_link_stats(db: Session, short_code: str) -> Link:
    link = repository.get_link_by_code(db, short_code)
    if link is None:
        raise LinkNotFoundError(f"Short code '{short_code}' not found.")
    return link
