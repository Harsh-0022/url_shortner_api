from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from valkey import Valkey

from url_shortener import service
from url_shortener.cache import get_valkey
from url_shortener.config import Settings, get_settings
from url_shortener.database import get_db
from url_shortener.schemas import LinkCreateRequest, LinkResponse, LinkStatsResponse

router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]
ValkeyClient = Annotated[Valkey, Depends(get_valkey)]


@router.post(
    "/api/v1/links",
    response_model=LinkResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Links"],
)
def shorten_url(
    payload: LinkCreateRequest,
    request: Request,
    db: DbSession,
    valkey_client: ValkeyClient,
    settings: AppSettings,
) -> LinkResponse:
    client_ip = request.client.host if request.client is not None else "unknown"
    try:
        link = service.create_short_link(db, valkey_client, payload, settings, client_ip)
    except service.RateLimitExceededError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except service.RedirectLoopError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except service.AliasConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except service.CodeGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    base = settings.base_url.rstrip("/")
    return LinkResponse(
        short_code=link.short_code,
        short_url=f"{base}/{link.short_code}",
        target_url=link.target_url,
        created_at=link.created_at,
        expires_at=link.expires_at,
    )


@router.get(
    "/api/v1/links/{short_code}/stats",
    response_model=LinkStatsResponse,
    tags=["Links"],
)
def read_link_stats(
    short_code: str,
    db: DbSession,
) -> LinkStatsResponse:
    try:
        link = service.get_link_stats(db, short_code)
    except service.LinkNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return LinkStatsResponse(
        short_code=link.short_code,
        target_url=link.target_url,
        clicks=link.clicks,
        created_at=link.created_at,
        expires_at=link.expires_at,
        is_expired=service.is_link_expired(link),
    )


@router.get("/{short_code}", tags=["Redirect"])
def redirect_to_target(
    short_code: str,
    db: DbSession,
    valkey_client: ValkeyClient,
    settings: AppSettings,
) -> RedirectResponse:
    try:
        target_url = service.resolve_redirect_target(db, valkey_client, short_code, settings)
    except service.LinkNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except service.LinkExpiredError as exc:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(exc)) from exc

    return RedirectResponse(url=target_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
