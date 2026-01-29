#!/usr/bin/env bash
set -euo pipefail

# Копирование файлов/папок с продакшена на локальную машину.
#
# Пример:
#   PROD_USER=root PROD_HOST=sec-scanner.pro PROD_PATH=/opt/sec-scanner ./scripts/pull_prod.sh
#
# Или с указанием конкретных путей:
#   ./scripts/pull_prod.sh /etc/nginx/sites-available/sec-scanner /var/www/sec-scanner

PROD_USER="${PROD_USER:-root}"
PROD_HOST="${PROD_HOST:-sec-scanner.pro}"
PROD_PORT="${PROD_PORT:-22}"
PROD_PATH="${PROD_PATH:-/opt/sec-scanner}"

DEST_DIR="${DEST_DIR:-./_prod_dump}"

mkdir -p "$DEST_DIR"

if ! command -v rsync >/dev/null 2>&1; then
  echo "rsync не найден. Установи rsync (в Ubuntu/WSL: sudo apt-get install -y rsync)"
  exit 1
fi

SSH_OPTS=(-p "$PROD_PORT" -o StrictHostKeyChecking=accept-new)

if [[ $# -gt 0 ]]; then
  echo "Копирую указанные пути в $DEST_DIR ..."
  for p in "$@"; do
    rsync -avz --delete -e "ssh ${SSH_OPTS[*]}" \
      "${PROD_USER}@${PROD_HOST}:${p}" \
      "${DEST_DIR}/"
  done
else
  echo "Копирую PROD_PATH=$PROD_PATH в $DEST_DIR ..."
  rsync -avz --delete -e "ssh ${SSH_OPTS[*]}" \
    "${PROD_USER}@${PROD_HOST}:${PROD_PATH}/" \
    "${DEST_DIR}/$(basename "$PROD_PATH")/"
fi

echo "Готово: $DEST_DIR"

