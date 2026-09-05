FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

# chanlun currently ships a mixed Python/Rust extension. Build its wheel in a
# disposable stage so the production image does not retain compilers/linkers.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml LICENSE alembic.ini /build/
COPY backend /build/backend
COPY config /build/config
COPY scripts /build/scripts

RUN pip wheel --no-cache-dir --wheel-dir /wheels ".[market]"


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
COPY --from=builder /wheels /wheels

# Install the project wheel produced by this exact build plus its market extras
# from the builder wheelhouse. Do not pin the application version here: the
# wheel filename/version is owned by pyproject.toml, and a second hard-coded
# Docker version can silently drift during a release. --no-index still keeps
# the runtime install confined to the audited wheelhouse.
RUN pip install --no-cache-dir --no-index --find-links=/wheels \
        "china-fund-decision[market]" \
    && rm -rf /wheels

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/reports /app/backups /var/lib/china-fund-decision/ocr-model \
    && chown -R appuser:appuser /app /var/lib/china-fund-decision
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
