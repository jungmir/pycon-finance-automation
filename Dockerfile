FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# /data is mounted as Railway Volume for SQLite persistence
RUN mkdir -p /data

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /data
USER appuser

CMD ["python", "-m", "src.main"]
