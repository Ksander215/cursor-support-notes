#!/usr/bin/env bash
set -euo pipefail

# Настройка автоматического деплоя на VPS

echo "🚀 Настройка автоматического деплоя на VPS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Проверка наличия SSH ключа
if [ ! -f ~/.ssh/id_rsa ] && [ ! -f ~/.ssh/id_ed25519 ]; then
    echo "⚠️  SSH ключ не найден. Создать новый? (y/n)"
    read -r answer
    if [ "$answer" = "y" ]; then
        ssh-keygen -t ed25519 -C "deploy@sec-scanner" -f ~/.ssh/id_ed25519
        echo "✅ SSH ключ создан: ~/.ssh/id_ed25519"
    fi
fi

# Определить SSH ключ
SSH_KEY=""
if [ -f ~/.ssh/id_ed25519 ]; then
    SSH_KEY=~/.ssh/id_ed25519
elif [ -f ~/.ssh/id_rsa ]; then
    SSH_KEY=~/.ssh/id_rsa
fi

echo ""
echo "📝 Введите данные VPS сервера:"
read -p "VPS Host (IP или домен): " VPS_HOST
read -p "VPS User (обычно root): " VPS_USER
read -p "Путь на VPS (обычно /opt/sec-scanner): " VPS_PATH_INPUT
VPS_PATH="${VPS_PATH_INPUT:-/opt/sec-scanner}"

# Создать файл конфигурации
CONFIG_FILE=".vps-deploy.env"
cat > "$CONFIG_FILE" <<EOF
# Конфигурация автоматического деплоя на VPS
# Этот файл содержит чувствительные данные - не коммитьте его в Git!

VPS_HOST=$VPS_HOST
VPS_USER=$VPS_USER
VPS_PATH=$VPS_PATH
SSH_KEY=$SSH_KEY
EOF

chmod 600 "$CONFIG_FILE"
echo "✅ Конфигурация сохранена в $CONFIG_FILE"

# Добавить в .gitignore
if ! grep -q "^\.vps-deploy\.env$" .gitignore 2>/dev/null; then
    echo ".vps-deploy.env" >> .gitignore
    echo "✅ Добавлено в .gitignore"
fi

# Копирование SSH ключа на VPS
echo ""
echo "🔑 Настройка SSH ключа на VPS..."

# Сначала проверить, может ли уже подключиться с этим ключом
if ssh -i "$SSH_KEY" -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o BatchMode=yes "$VPS_USER@$VPS_HOST" "echo 'SSH OK'" 2>/dev/null; then
    echo "✅ SSH ключ уже настроен и работает!"
else
    echo "⚠️  SSH ключ еще не настроен на VPS"
    echo ""
    echo "📋 Ваш публичный SSH ключ:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    cat "${SSH_KEY}.pub"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "📝 Скопируйте ключ выше и добавьте его на VPS одним из способов:"
    echo ""
    echo "🔹 Способ 1: Если у вас есть доступ через другой SSH ключ"
    echo "   Подключитесь к VPS с существующим ключом и выполните:"
    echo "   ssh -i /path/to/existing/key $VPS_USER@$VPS_HOST"
    echo "   Затем на VPS:"
    echo "   mkdir -p ~/.ssh"
    echo "   chmod 700 ~/.ssh"
    echo "   nano ~/.ssh/authorized_keys"
    echo "   # Вставьте ключ выше, сохраните (Ctrl+O, Enter, Ctrl+X)"
    echo "   chmod 600 ~/.ssh/authorized_keys"
    echo ""
    echo "🔹 Способ 2: Через веб-консоль VPS провайдера"
    echo "   1. Войдите в панель управления VPS"
    echo "   2. Откройте веб-консоль/терминал"
    echo "   3. Выполните команды выше"
    echo ""
    echo "🔹 Способ 3: Если пароль временно включен"
    echo "   cat ${SSH_KEY}.pub | ssh $VPS_USER@$VPS_HOST 'mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'"
    echo ""
    read -p "Нажмите Enter после добавления ключа на VPS..."
fi

# Тест подключения
echo ""
echo "🔍 Тестирование подключения..."
if ssh -i "$SSH_KEY" -o ConnectTimeout=5 -o BatchMode=yes "$VPS_USER@$VPS_HOST" "echo 'SSH OK'" 2>/dev/null; then
    echo "✅ SSH подключение работает!"
else
    echo "❌ SSH подключение не работает. Проверьте настройки."
    exit 1
fi

# Обновить скрипт auto-deploy.sh для использования конфига
if [ -f scripts/auto-deploy.sh ]; then
    # Добавить загрузку конфига в начало скрипта
    if ! grep -q "\.vps-deploy\.env" scripts/auto-deploy.sh; then
        sed -i '/^set -euo pipefail/a\
# Load config if exists\
if [ -f .vps-deploy.env ]; then\
    set -a\
    source .vps-deploy.env\
    set +a\
fi' scripts/auto-deploy.sh
        echo "✅ Скрипт auto-deploy.sh обновлен"
    fi
fi

echo ""
echo "✅ Настройка завершена!"
echo ""
echo "📖 Использование:"
echo "   # Деплой всех сервисов"
echo "   ./scripts/auto-deploy.sh"
echo ""
echo "   # Деплой только frontend"
echo "   ./scripts/auto-deploy.sh --frontend-only"
echo ""
echo "   # Деплой только API"
echo "   ./scripts/auto-deploy.sh --api-only"
echo ""
echo "   # Тестовый запуск (без реального деплоя)"
echo "   ./scripts/auto-deploy.sh --dry-run"
echo ""
