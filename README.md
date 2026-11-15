
# URL Shortener & Click Analytics Microservice

A layered, production-oriented URL shortener built with **FastAPI**, **Valkey**, **SQLAlchemy 2.0**, and **Pydantic V2**.

## Architecture & Key Features
- **Layered Separation:** Clean boundaries across `router`, `service`, `repository`, `cache`, `models`, and `schemas`.
- **Base62 Short Codes & Custom Aliases:** Cryptographically random Base62 generation with bounded `IntegrityError` collision retries, reserved path protection, and redirect-loop prevention.
- **Valkey Read-Through Caching & Rate Limiting:** Sub-millisecond redirect lookups with TTL bounds synced to link expiration, plus atomic IP sliding-window rate limiting (`429 Too Many Requests`) and graceful SQLite fallback if Valkey is unavailable.
- **Atomic Analytics & TTL Expiration:** SQL-level atomic click increments (`clicks + 1`) on SQLite in WAL mode, returning `410 Gone` for expired links.
- **Observability & Quality Gates:** `X-Request-ID` latency logging middleware, `mypy --strict`, `ruff`, `pytest` + `fakeredis` integration tests, GitHub Actions CI, and non-root multi-stage Docker Compose deployment.

## Quickstart (Docker Compose)

```bash
docker compose up --build -d
curl -s http://localhost:8000/health
