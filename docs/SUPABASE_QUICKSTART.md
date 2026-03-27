# Supabase Quickstart Guide

## Шаг 1: Создание проекта

1. Зайдите на https://supabase.com
2. Создайте новый проект:
   - **Name:** `sec-scanner-prod`
   - **Region:** `EU Central` (Frankfurt) — ближайший к VPS
   - **Database Password:** сохраните надёжно!
3. Дождитесь создания (2-3 минуты)

## Шаг 2: Получение credentials

В Project Settings > API:

```bash
# Connection String (Session mode, порт 6543)
SEC_SCANNER_DATABASE_URL=postgresql+psycopg://postgres.[PROJECT_REF]:[PASSWORD]@aws-0-eu-central-1.pooler.supabase.com:6543/postgres

# API URL
SUPABASE_URL=https://[PROJECT_REF].supabase.co

# Keys
SUPABASE_SERVICE_ROLE_KEY=eyJ...    # service_role key
SUPABASE_ANON_KEY=eyJ...            # anon key
```

## Шаг 3: Применение миграций

### Вариант A: Через Alembic (рекомендуется)

```bash
# На локальной машине или VPS
export SEC_SCANNER_DATABASE_URL="postgresql+psycopg://postgres.[PROJECT_REF]:[PASSWORD]@aws-0-eu-central-1.pooler.supabase.com:6543/postgres"
alembic upgrade head
```

### Вариант B: Через Supabase CLI

```bash
supabase login
supabase link --project-ref [PROJECT_REF]
supabase db push
```

## Шаг 4: Обновление .env на VPS

```bash
# /opt/sec-scanner/.env
SEC_SCANNER_DATABASE_URL=postgresql+psycopg://postgres.[PROJECT_REF]:[PASSWORD]@aws-0-eu-central-1.pooler.supabase.com:6543/postgres
SUPABASE_URL=https://[PROJECT_REF].supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...
```

## Шаг 5: Рестарт приложения

```bash
cd /opt/sec-scanner
docker compose down
docker compose up -d
```

## Шаг 6: Инициализация дефолтных данных

```bash
docker exec -it sec-scanner-api python -m scripts.init_default_plans
```

## Структура БД после миграций

### Alembic миграции (основное приложение):
- `audits` — результаты сканирований
- `organizations` — организации
- `api_keys` — API ключи
- `plans` — тарифные планы
- `leads` — лиды
- `payments` — платежи
- `webhooks` — вебхуки

### Supabase миграции (AI Orchestrator):
- `agent_tasks` — очередь задач
- `agent_registry` — реестр агентов
- `task_history` — история задач

## Проверка

```sql
-- В Supabase SQL Editor
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;
```

Должны появиться все таблицы из Alembic миграций.

## Troubleshooting

### Connection refused
- Проверьте, что IP VPS добавлен в Supabase > Settings > API > Allowed IPs
- Или разрешите все IP (не рекомендуется для продакшена)

### SSL error
- Добавьте `?sslmode=require` к connection string

### Migration fails
- Проверьте логи: `alembic history` и `alembic current`
- Убедитесь, что `alembic_version` таблица создана