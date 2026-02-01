#!/bin/bash
# Скрипт проверки готовности к production деплою
# Использование: bash scripts/check_production_readiness.sh

set -e

echo "🔍 Проверка готовности к production деплою..."
echo ""

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ERRORS=0
WARNINGS=0

# Функция для проверки наличия файла
check_file() {
    if [ -f "$1" ]; then
        echo -e "${GREEN}✅${NC} $2: найден"
        return 0
    else
        echo -e "${RED}❌${NC} $2: не найден"
        ERRORS=$((ERRORS + 1))
        return 1
    fi
}

# Функция для проверки переменной окружения
check_env_var() {
    if grep -q "^$1=" .env.production 2>/dev/null; then
        VALUE=$(grep "^$1=" .env.production | cut -d'=' -f2- | tr -d ' ')
        if [ -z "$VALUE" ] || [ "$VALUE" = "CHANGE_ME" ] || [ "$VALUE" = "..." ]; then
            echo -e "${YELLOW}⚠️${NC} $2: не настроен (значение по умолчанию)"
            WARNINGS=$((WARNINGS + 1))
            return 1
        else
            echo -e "${GREEN}✅${NC} $2: настроен"
            return 0
        fi
    else
        echo -e "${RED}❌${NC} $2: отсутствует в .env.production"
        ERRORS=$((ERRORS + 1))
        return 1
    fi
}

# Функция для проверки миграций
check_migrations() {
    echo ""
    echo "📊 Проверка миграций БД..."

    if command -v alembic &> /dev/null; then
        CURRENT=$(alembic current 2>/dev/null | grep -oP '\(head\)|\([a-f0-9]+\)' | head -1 || echo "unknown")
        echo -e "${GREEN}✅${NC} Alembic доступен"
        echo "   Текущая версия: $CURRENT"

        # Проверка наличия миграции для планов
        if [ -f "alembic/versions/20260129_0005_default_pricing_plans.py" ]; then
            echo -e "${GREEN}✅${NC} Миграция для планов найдена"
        else
            echo -e "${RED}❌${NC} Миграция для планов не найдена"
            ERRORS=$((ERRORS + 1))
        fi
    else
        echo -e "${YELLOW}⚠️${NC} Alembic не установлен (проверка пропущена)"
        WARNINGS=$((WARNINGS + 1))
    fi
}

# Функция для проверки Docker
check_docker() {
    echo ""
    echo "🐳 Проверка Docker..."

    if command -v docker &> /dev/null; then
        echo -e "${GREEN}✅${NC} Docker доступен"

        if docker ps &> /dev/null; then
            echo -e "${GREEN}✅${NC} Docker daemon работает"
        else
            echo -e "${RED}❌${NC} Docker daemon не работает"
            ERRORS=$((ERRORS + 1))
        fi
    else
        echo -e "${RED}❌${NC} Docker не установлен"
        ERRORS=$((ERRORS + 1))
    fi
}

# Функция для проверки Stripe конфигурации
check_stripe() {
    echo ""
    echo "💳 Проверка Stripe конфигурации..."

    check_env_var "STRIPE_SECRET_KEY" "Stripe Secret Key"
    check_env_var "STRIPE_WEBHOOK_SECRET" "Stripe Webhook Secret"
    check_env_var "STRIPE_PRICE_FREE" "Stripe Price ID (Free)"
    check_env_var "STRIPE_PRICE_STARTER" "Stripe Price ID (Starter)"
    check_env_var "STRIPE_PRICE_PROFESSIONAL" "Stripe Price ID (Professional)"
    check_env_var "STRIPE_PRICE_ENTERPRISE" "Stripe Price ID (Enterprise)"
}

# Основные проверки
echo "📁 Проверка файлов проекта..."
check_file ".env.production" ".env.production"
check_file "docker-compose.prod.yml" "docker-compose.prod.yml"
check_file "alembic.ini" "alembic.ini"
check_file "requirements.txt" "requirements.txt"

# Проверка критичных переменных окружения
echo ""
echo "🔐 Проверка критичных переменных окружения..."

if [ ! -f ".env.production" ]; then
    echo -e "${RED}❌${NC} Файл .env.production не найден!"
    echo "   Создайте его на основе .env.production.example"
    ERRORS=$((ERRORS + 1))
else
    check_env_var "POSTGRES_PASSWORD" "PostgreSQL Password"
    check_env_var "SEC_SCANNER_API_KEY_PEPPER" "API Key Pepper"
    check_env_var "SEC_SCANNER_REQUIRE_API_KEY" "Require API Key"

    # Проверка значения SEC_SCANNER_REQUIRE_API_KEY
    REQUIRE_API_KEY=$(grep "^SEC_SCANNER_REQUIRE_API_KEY=" .env.production | cut -d'=' -f2- | tr -d ' ')
    if [ "$REQUIRE_API_KEY" != "true" ]; then
        echo -e "${YELLOW}⚠️${NC} SEC_SCANNER_REQUIRE_API_KEY должен быть 'true' в production"
        WARNINGS=$((WARNINGS + 1))
    fi
fi

# Проверка Stripe
check_stripe

# Проверка миграций
check_migrations

# Проверка Docker
check_docker

# Проверка зависимостей Python
echo ""
echo "🐍 Проверка Python зависимостей..."
if [ -f "requirements.txt" ]; then
    if command -v pip &> /dev/null; then
        echo -e "${GREEN}✅${NC} pip доступен"

        # Проверка критичных зависимостей
        if pip show stripe &> /dev/null; then
            echo -e "${GREEN}✅${NC} stripe установлен"
        else
            echo -e "${YELLOW}⚠️${NC} stripe не установлен (установите: pip install -r requirements.txt)"
            WARNINGS=$((WARNINGS + 1))
        fi

        if pip show weasyprint &> /dev/null; then
            echo -e "${GREEN}✅${NC} weasyprint установлен (для PDF экспорта)"
        else
            echo -e "${YELLOW}⚠️${NC} weasyprint не установлен (установите: pip install -r requirements.txt)"
            WARNINGS=$((WARNINGS + 1))
        fi
    else
        echo -e "${YELLOW}⚠️${NC} pip не найден"
        WARNINGS=$((WARNINGS + 1))
    fi
fi

# Проверка Nmap
echo ""
echo "🔍 Проверка Nmap..."
if command -v nmap &> /dev/null; then
    NMAP_VERSION=$(nmap --version | head -1 || echo "unknown")
    echo -e "${GREEN}✅${NC} Nmap установлен: $NMAP_VERSION"
else
    echo -e "${YELLOW}⚠️${NC} Nmap не установлен (опционально, но рекомендуется)"
    echo "   Для расширенного сканирования портов установите: apt-get install nmap"
    WARNINGS=$((WARNINGS + 1))
fi

# Итоговый отчет
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Итоговый отчет:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✅ Все проверки пройдены!${NC}"
    echo "   Проект готов к production деплою."
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}⚠️ Найдено предупреждений: $WARNINGS${NC}"
    echo "   Проект готов к деплою, но рекомендуется исправить предупреждения."
    exit 0
else
    echo -e "${RED}❌ Найдено ошибок: $ERRORS${NC}"
    if [ $WARNINGS -gt 0 ]; then
        echo -e "${YELLOW}⚠️ Найдено предупреждений: $WARNINGS${NC}"
    fi
    echo ""
    echo "Пожалуйста, исправьте ошибки перед деплоем."
    echo ""
    echo "Следующие шаги:"
    echo "1. Настройте Stripe аккаунт (см. STRIPE_SETUP_GUIDE.md)"
    echo "2. Обновите .env.production со всеми необходимыми переменными"
    echo "3. Примените миграции БД: alembic upgrade head"
    echo "4. Протестируйте локально перед деплоем"
    exit 1
fi
