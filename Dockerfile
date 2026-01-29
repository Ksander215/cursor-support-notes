ARG DOCKER_LIBRARY_REGISTRY=docker.io/library
FROM ${DOCKER_LIBRARY_REGISTRY}/python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends openssl ca-certificates bash \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app.py /app/app.py
COPY src /app/src
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic
COPY scripts /app/scripts

RUN chmod +x /app/scripts/start_api.sh

ENV SEC_SCANNER_DB_PATH=/app/data/sec_scanner.db
RUN mkdir -p /app/data

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

