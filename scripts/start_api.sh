#!/usr/bin/env bash
set -euo pipefail

cd /app

echo "[sec-scanner] Running migrations..."
alembic upgrade head

echo "[sec-scanner] Starting API..."
exec uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}"

