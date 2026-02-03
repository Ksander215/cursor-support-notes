#!/usr/bin/env bash
set -euo pipefail

# Скрипт для автоматического обновления Stripe конфигурации в .env.production на VPS
# Использование: ./scripts/update_stripe_config.sh stripe_tokens.txt

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TOKENS_FILE="${1:-$PROJECT_ROOT/stripe_tokens.txt}"

if [[ ! -f "$TOKENS_FILE" ]]; then
    echo "❌ Ошибка: файл $TOKENS_FILE не найден"
    echo ""
    echo "Использование: $0 <путь_к_файлу_с_токенами>"
    echo "Пример: $0 stripe_tokens.txt"
    exit 1
fi

echo "🔧 Обновление Stripe конфигурации на VPS"
echo "=========================================="
echo ""

# Проверка подключения к VPS
if ! grep -q "VPS_HOST" "$PROJECT_ROOT/.vps-deploy.env" 2>/dev/null; then
    echo "❌ Ошибка: файл .vps-deploy.env не найден"
    echo "   Убедитесь, что файл существует и содержит VPS_HOST, VPS_USER, SSH_KEY"
    exit 1
fi

# Загрузить переменные из .vps-deploy.env
set -a
# shellcheck disable=SC1090,SC1091
. "$PROJECT_ROOT/.vps-deploy.env"
set +a

VPS_HOST="${VPS_HOST:-}"
VPS_USER="${VPS_USER:-root}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519}"
VPS_PATH="${VPS_PATH:-/opt/sec-scanner}"

if [[ -z "$VPS_HOST" ]]; then
    echo "❌ Ошибка: VPS_HOST не установлен в .vps-deploy.env"
    exit 1
fi

echo "📋 Чтение токенов из файла..."
echo ""

# Извлечь значения из файла токенов
STRIPE_SECRET_KEY=""
STRIPE_WEBHOOK_SECRET=""
STRIPE_PRICE_FREE=""
STRIPE_PRICE_STARTER=""
STRIPE_PRICE_PROFESSIONAL=""
STRIPE_PRICE_ENTERPRISE=""

while IFS='=' read -r key value || [[ -n "$key" ]]; do
    # Пропустить комментарии и пустые строки
    [[ "$key" =~ ^#.*$ ]] && continue
    [[ -z "$key" ]] && continue

    # Убрать пробелы
    key=$(echo "$key" | xargs)
    value=$(echo "$value" | xargs)

    case "$key" in
        STRIPE_SECRET_KEY)
            STRIPE_SECRET_KEY="$value"
            ;;
        STRIPE_WEBHOOK_SECRET)
            STRIPE_WEBHOOK_SECRET="$value"
            ;;
        STRIPE_PRICE_FREE)
            STRIPE_PRICE_FREE="$value"
            ;;
        STRIPE_PRICE_STARTER)
            STRIPE_PRICE_STARTER="$value"
            ;;
        STRIPE_PRICE_PROFESSIONAL)
            STRIPE_PRICE_PROFESSIONAL="$value"
            ;;
        STRIPE_PRICE_ENTERPRISE)
            STRIPE_PRICE_ENTERPRISE="$value"
            ;;
    esac
done < "$TOKENS_FILE"

# Проверка обязательных полей
if [[ -z "$STRIPE_SECRET_KEY" ]] || [[ "$STRIPE_SECRET_KEY" == "sk_test_..." ]]; then
    echo "❌ Ошибка: STRIPE_SECRET_KEY не заполнен или содержит placeholder"
    exit 1
fi

if [[ -z "$STRIPE_WEBHOOK_SECRET" ]] || [[ "$STRIPE_WEBHOOK_SECRET" == "whsec_..." ]]; then
    echo "❌ Ошибка: STRIPE_WEBHOOK_SECRET не заполнен или содержит placeholder"
    exit 1
fi

echo "✅ Токены прочитаны:"
echo "   STRIPE_SECRET_KEY: ${STRIPE_SECRET_KEY:0:20}..."
echo "   STRIPE_WEBHOOK_SECRET: ${STRIPE_WEBHOOK_SECRET:0:20}..."
echo "   STRIPE_PRICE_STARTER: ${STRIPE_PRICE_STARTER:-не установлен}"
echo "   STRIPE_PRICE_PROFESSIONAL: ${STRIPE_PRICE_PROFESSIONAL:-не установлен}"
echo ""

# Подключение к VPS и обновление .env.production
echo "🔌 Подключение к VPS ($VPS_USER@$VPS_HOST)..."
echo ""

ENV_FILE="$VPS_PATH/.env.production"

# Создать временный скрипт для выполнения на VPS
TEMP_SCRIPT=$(mktemp)
cat > "$TEMP_SCRIPT" << 'ENDOFSCRIPT'
#!/bin/bash
set -euo pipefail

ENV_FILE="$1"
shift

# Создать backup
if [[ -f "$ENV_FILE" ]]; then
    BACKUP_FILE="${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
    cp "$ENV_FILE" "$BACKUP_FILE"
    echo "✅ Backup создан: $BACKUP_FILE"
fi

# Обновить или добавить Stripe переменные
for var_line in "$@"; do
    var_name=$(echo "$var_line" | cut -d'=' -f1)
    var_value=$(echo "$var_line" | cut -d'=' -f2-)

    # Удалить старую строку если существует
    if grep -q "^${var_name}=" "$ENV_FILE" 2>/dev/null; then
        sed -i "/^${var_name}=/d" "$ENV_FILE"
    fi

    # Добавить новую строку
    echo "${var_name}=${var_value}" >> "$ENV_FILE"
done

echo "✅ .env.production обновлен"
ENDOFSCRIPT

chmod +x "$TEMP_SCRIPT"

# Передать переменные в скрипт
VAR_LINES=(
    "STRIPE_SECRET_KEY=$STRIPE_SECRET_KEY"
    "STRIPE_WEBHOOK_SECRET=$STRIPE_WEBHOOK_SECRET"
)

[[ -n "$STRIPE_PRICE_FREE" ]] && VAR_LINES+=("STRIPE_PRICE_FREE=$STRIPE_PRICE_FREE")
[[ -n "$STRIPE_PRICE_STARTER" ]] && VAR_LINES+=("STRIPE_PRICE_STARTER=$STRIPE_PRICE_STARTER")
[[ -n "$STRIPE_PRICE_PROFESSIONAL" ]] && VAR_LINES+=("STRIPE_PRICE_PROFESSIONAL=$STRIPE_PRICE_PROFESSIONAL")
[[ -n "$STRIPE_PRICE_ENTERPRISE" ]] && VAR_LINES+=("STRIPE_PRICE_ENTERPRISE=$STRIPE_PRICE_ENTERPRISE")

# Выполнить скрипт на VPS
echo "📝 Обновление .env.production на VPS..."
ssh -i "$SSH_KEY" "$VPS_USER@$VPS_HOST" bash -s -- "$ENV_FILE" "${VAR_LINES[@]}" < "$TEMP_SCRIPT"

# Удалить временный скрипт
rm -f "$TEMP_SCRIPT"

echo ""
echo "🔄 Перезапуск контейнеров..."
ssh -i "$SSH_KEY" "$VPS_USER@$VPS_HOST" "cd $VPS_PATH && docker compose -f docker-compose.prod.yml restart api worker"

echo ""
echo "✅ Проверка загруженных переменных..."
ssh -i "$SSH_KEY" "$VPS_USER@$VPS_HOST" "cd $VPS_PATH && docker compose -f docker-compose.prod.yml exec -T api env | grep STRIPE || echo 'Переменные не найдены'"

echo ""
echo "✅ Готово! Stripe конфигурация обновлена на VPS"
echo ""
echo "📝 Следующие шаги:"
echo "   1. Проверьте логи: docker logs sec-scanner-api-1 | grep -i stripe"
echo "   2. Протестируйте checkout: curl -X POST https://api.sec-scanner.pro/payments/checkout ..."
