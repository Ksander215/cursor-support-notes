#!/usr/bin/env bash
set -euo pipefail

# Deploy from /opt/sec-scanner (archive unpacked here)

cd /opt/sec-scanner

if [ ! -f .env.production ]; then
  echo "Missing .env.production. Create it from .env.production.example"
  exit 1
fi

chmod +x ./scripts/*.sh || true

set -a
. ./.env.production
set +a

echo "[1/2] start stack"
docker-compose --env-file .env.production -f docker-compose.prod.yml up --build -d

echo "[2/2] status"
docker-compose -f docker-compose.prod.yml ps

echo "API should be on :8000 (localhost). Next: nginx+ssl"
