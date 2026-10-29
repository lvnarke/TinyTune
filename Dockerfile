FROM grafana/k6:0.54.0 AS k6
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv/tinytune

RUN useradd --create-home --uid 10001 appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY db ./db
COPY scripts ./scripts
COPY frontend ./frontend
COPY --from=k6 /usr/bin/k6 /usr/local/bin/k6

RUN mkdir -p /srv/tinytune/results && chown -R appuser:appuser /srv/tinytune

USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

