FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/backend \
    TZ=Asia/Shanghai

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml LICENSE alembic.ini /app/
COPY backend /app/backend
COPY config /app/config
COPY scripts /app/scripts

RUN pip install --no-cache-dir ".[market]"

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/reports /app/backups /var/lib/china-fund-decision/ocr-model \
    && chown -R appuser:appuser /app /var/lib/china-fund-decision
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
