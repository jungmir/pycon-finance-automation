FROM python:3.13-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src/ ./src/

# /data is mounted as Railway Volume for SQLite persistence
RUN mkdir -p /data && useradd -m -u 1000 appuser && chown -R appuser:appuser /data
USER appuser

CMD ["uv", "run", "python", "-m", "src.main"]
