#!/bin/bash
# Восстанавливает секцию db в docker-compose.prod.yml на VPS.
# Запуск на VPS: bash fix_docker_compose_db.sh

set -e
COMPOSE="/opt/sec-scanner/docker-compose.prod.yml"
cd "$(dirname "$COMPOSE")"
cp -a "$COMPOSE" "${COMPOSE}.bak"

# Правильное начало файла (services + db до volumes включительно)
HEAD='services:
  db:
    image: "${DOCKER_LIBRARY_REGISTRY:-docker.io/library}/postgres:15-alpine"
    environment:
      POSTGRES_DB: sec_scanner
      POSTGRES_USER: sec_scanner
      POSTGRES_PASSWORD: "${POSTGRES_PASSWORD:?}"
    volumes:
      - pgdata:/var/lib/postgresql/data
'

# Найти строку "    ports:" и взять всё начиная с неё
awk -v head="$HEAD" '
  BEGIN { done=0 }
  /^    ports:/ && done==0 { printf "%s", head; print; done=1; next }
  done==1 { print }
' "$COMPOSE" > "${COMPOSE}.new" && mv "${COMPOSE}.new" "$COMPOSE"
echo "Done. Backup: ${COMPOSE}.bak"
head -15 "$COMPOSE"
