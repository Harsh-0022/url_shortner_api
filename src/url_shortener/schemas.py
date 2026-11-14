import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from url_shortener.config import get_settings

ALIAS_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")


class LinkCreateRequest(BaseModel):
    target_url: HttpUrl
    custom_alias: str | None = Field(default=None, min_length=3, max_length=20)
    expires_in_hours: int | None = Field(default=None, ge=1, le=24 * 365)

    @field_validator("custom_alias")
    @classmethod
    def validate_custom_alias(cls, value: str | None) -> str | None:
        if value is None:
            return None

        if not ALIAS_PATTERN.match(value):
            raise ValueError(
                "Custom alias must be 3-20 characters (letters, numbers, hyphens, underscores)"
            )

        reserved = get_settings().reserved_aliases
        if value.lower() in reserved:
            raise ValueError(f"Alias '{value}' is reserved and cannot be used.")

        return value


class LinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    short_code: str
    short_url: str
    target_url: str
    created_at: datetime
    expires_at: datetime | None


class LinkStatsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    short_code: str
    target_url: str
    clicks: int
    created_at: datetime
    expires_at: datetime | None
    is_expired: bool
