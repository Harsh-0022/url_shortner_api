import logging
from functools import lru_cache
from typing import cast

from valkey import Valkey
from valkey.exceptions import ValkeyError

from url_shortener.config import get_settings

logger = logging.getLogger("url_shortener.cache")


@lru_cache
def get_valkey() -> Valkey:
    settings = get_settings()
    return Valkey.from_url(
        settings.valkey_url,
        decode_responses=True,
        socket_connect_timeout=1.0,
        socket_timeout=1.0,
    )


def ping_valkey(client: Valkey) -> bool:
    try:
        return bool(client.ping())
    except ValkeyError:
        return False


def get_cached_target(client: Valkey, short_code: str) -> str | None:
    try:
        value = client.get(f"link:target:{short_code}")
        return str(value) if value is not None else None
    except ValkeyError as exc:
        logger.warning("Valkey read failed for short_code=%s: %s", short_code, exc)
        return None


def set_cached_target(
    client: Valkey,
    short_code: str,
    target_url: str,
    ttl_seconds: int,
) -> None:
    if ttl_seconds <= 0:
        return
    try:
        client.set(f"link:target:{short_code}", target_url, ex=ttl_seconds)
    except ValkeyError as exc:
        logger.warning("Valkey write failed for short_code=%s: %s", short_code, exc)


def is_rate_limited(
    client: Valkey,
    client_ip: str,
    max_requests: int,
    window_seconds: int,
) -> bool:
    key = f"ratelimit:create:{client_ip}"
    try:
        current_count = cast(int, client.incr(key))
        if current_count == 1:
            client.expire(key, window_seconds)
        return current_count > max_requests
    except ValkeyError as exc:
        logger.warning("Valkey rate-limit check failed for ip=%s: %s", client_ip, exc)
        return False
