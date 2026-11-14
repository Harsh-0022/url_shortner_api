FROM python:3.10-slim AS builder

WORKDIR /build
COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.10-slim AS runtime

RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app
COPY --from=builder /install /usr/local
COPY src/ src/

RUN mkdir -p /app/data && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["uvicorn", "url_shortener.main:app", "--host", "0.0.0.0", "--port", "8000"]
