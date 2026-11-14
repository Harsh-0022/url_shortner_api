import logging
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from valkey import Valkey

from url_shortener import models  # noqa: F401
from url_shortener.cache import get_valkey, ping_valkey
from url_shortener.config import get_settings
from url_shortener.database import Base, engine, get_db
from url_shortener.router import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("url_shortener")

DbSession = Annotated[Session, Depends(get_db)]
ValkeyClient = Annotated[Valkey, Depends(get_valkey)]


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    Base.metadata.create_all(bind=engine)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def request_logging_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        start_time = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start_time) * 1000

        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_id=%s method=%s path=%s status=%d duration_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on path=%s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An unexpected internal server error occurred."},
        )

    @app.get("/health", tags=["Health"])
    def health_check(db: DbSession, valkey_client: ValkeyClient) -> dict[str, str]:
        try:
            db.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database connection failed",
            ) from exc

        valkey_status = "connected" if ping_valkey(valkey_client) else "unavailable"
        return {
            "status": "healthy",
            "database": "connected",
            "valkey": valkey_status,
        }

    app.include_router(router)
    return app


app = create_app()
