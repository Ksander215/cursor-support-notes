# MAIN_AGENT — журнал статуса (Cursor / OpenCode)

Использование: *«Прочитай MAIN_AGENT.md и продолжай с последнего места»* — восстанавливает контекст между сессиями. Детальный индекс: [`AGENTS.md`](AGENTS.md).

Обновляйте этот файл при **handoff** между инструментами или людьми: кратко, по пунктам.

**Делегирование OpenCode:** полный шаблон промпта — [.cursor/skills/opencode-project-skills/SKILL.md](.cursor/skills/opencode-project-skills/SKILL.md) (*Делегирование из Cursor*). Cursor может оставаться оркестратором; объём — в OpenCode.

---

## Пакет для OpenCode (копипаст)

*Заполняйте перед передачей задачи в OpenCode; после выполнения — краткий итог в «Последние решения».*

Шаблон handoff-ready для карточек Vibe Kanban: `agent_outputs/VIBE_HANDOFF_TEMPLATE.md`

**Цель (техника — ведёт OpenCode, апр. 2026):** поддержка локального outbound-дайджеста, согласованность скриптов с CSV, прогон тестов/линтера; стратегия продаж и тексты — у человека + Cursor по запросу.

**Контекст (файлы, эндпоинты, доки):**

- `scripts/outbound_daily_digest.py` — дайджест по `agent_outputs/OUTBOUND_72H_TRACKER.csv` (warm/hot, опционально contacted; `next_step_at <= today`).
- `agent_outputs/MESSAGES_TO_SEND_TODAY.md` — ручной список + инструкция пост-обновления CSV (`notes`, `next_step`, `next_step_at`, `status`).
- `scripts/cash_autopilot.py`, `scripts/revenue_kpi_report.py` — опционально **выровнять документацию и при желании колонки** с тем, что в CSV сейчас нет обязательных `replied`/`replied_at` (скрипты уже backward-compatible).
- Индекс репо: `AGENTS.md`; провайдеры/MCP: `opencode.json`.

**Ограничения (не трогать / обязательные команды):**

- Не менять публичные API SaaS без явной задачи.
- После правок Python: `ruff check`, при необходимости `pytest` из корня (см. `AGENTS.md`).

**Критерии готовности (что считать «сделано»):**

- `python scripts/outbound_daily_digest.py --help` и прогон с `--today YYYY-MM-DD` без ошибок.
- Нет противоречий между описанием колонок в `MESSAGES_TO_SEND_TODAY.md` и фактическим заголовком CSV (или добавлен явный opt-in блок колонок `replied` в CSV — по решению).
- Краткая строка в «Последние решения» с датой.

**Промпты для OpenCode (выбери один; Plan → Build по необходимости)**

*A. Только дайджест (5–15 мин):*

```
Корень: ~/fastapi-project. Прочитай AGENTS.md (команды проверки).

Задача: scripts/outbound_daily_digest.py работает без сюрпризов.
Сделай: запуск --help; прогон с --today 2026-04-08 --limit 5 и с --include-contacted; при багах — минимальный фикс.
Готово если: stdout осмысленный, exit 0.
Итог: одна строка в MAIN_AGENT.md → «Последние решения».
```

*B. CSV ↔ автопилот / KPI (15–30 мин):*

```
Корень: ~/fastapi-project.

Задача: OUTBOUND_72H_TRACKER.csv, MESSAGES_TO_SEND_TODAY.md, cash_autopilot.py, revenue_kpi_report.py — одна правда по колонкам (replied/replied_at опциональны; без ломания backward-compat).
Сделай: выровняй комментарии/docstring или одну строку в MESSAGES/MAIN при противоречиях; не трогай публичный API.
Готово если: ruff на затронутых файлах; py_compile или короткий прогон скриптов по желанию.
Итог: строка в «Последние решения».
```

*C. Всё сразу (если не хочешь двух заходов):*

```
~/fastapi-project. AGENTS.md + этот раздел MAIN_AGENT.md.
Сделай A, затем B в одной сессии. Итог — одна строка в «Последние решения».
```

*D. n8n на VPS через OpenCode (SSH + Docker) — Plan → Build:*

```
Репозиторий локально: ~/fastapi-project (WSL). На проде путь и SSH — docs/SERVER_SSH_ACCESS.md и раздел «SSH Access» ниже.

Цель: поднять или восстановить n8n после работ хостера; зафиксировать факт в «Последние решения».

Сделай по шагам (bash, read-only сначала):
1. Прочитай docs/SERVER_SSH_ACCESS.md — хост, порт, путь /opt/sec-scanner.
2. SSH: проверь docker (`docker ps`), сеть `docker network ls` (для docker-compose.n8n.yml нужна external сеть `data` — если нет: `docker network create data`).
3. На сервере: `cd /opt/sec-scanner && git status && git pull` (если репо там). Проверь наличие `.env` с N8N_USER, N8N_PASSWORD, N8N_DB_PASSWORD (без вывода секретов в лог).
4. Запуск основного стека n8n: `docker compose -f docker-compose.n8n.yml up -d` (или из каталога, где лежит compose). Дождись healthy: `docker compose -f docker-compose.n8n.yml ps` и `curl -fsS http://127.0.0.1:5678/healthz` на сервере.
5. Если compose.n8n.yml не подходит (нет сети data / другой VPS): разверни автономно из репо — `docker-compose.n8n-standalone.yml`, скопируй `.env.n8n.example` → `.env.n8n` на сервере, выставь WEBHOOK_URL/N8N_EDITOR_BASE_URL с публичным URL или IP:5678, `docker compose -f docker-compose.n8n-standalone.yml --env-file .env.n8n up -d`.
6. Не коммить секреты. Если трогал токены — напомни ротировать в BotFather.
7. Итог: одна строка в «Последние решения» (дата, что поднято, URL/порт, какой compose файл).

Ограничения: не удалять чужие volumes без явного указания; не публиковать пароли в чат OpenCode — только факт успеха/ошибки.
```

---

## Сейчас в работе

- **Задача:** Freelance toolkit + отклики на биржах + BrowserAct интеграция
- **Цель на день:** Откликнуться на 5 заказов на FL.ru + 3 на Kwork
- **Ведущий:** Человек (продажи) + OpenCode (техника)
- **Ветка / PR:** main
- **Handoff:** `agent_outputs/HANDOFF_2026-04-14.md`

**Биржи:**
- FL.ru ✅ (профиль заполнен, Python/API/n8n, 1000₽/час)
- Kwork ✅ (3 кворка: Telegram бот 3000₽, API интеграция 5000₽, Аудит API 5000₽)
- Freelancehunt ❌ (забанен)

**Действия сегодня:**
1. Откликнуться на 5 заказов на FL.ru (шаблоны: freelance/FREELANCE_RESPONSES.md)
2. Откликнуться на 3 заказа на Kwork
3. Записать каждый отклик в трекер: `python3 freelance/add_order.py`
4. Настроить Telegram бот (FREELANCE_BOT_TOKEN + FREELANCE_CHAT_ID)
5. Исследовать BrowserAct для парсинга бирж

---

## Последние решения

- **14.04.2026** — Freelance toolkit завершён: FL.ru + Kwork профили заполнены, 3 кворка созданы, Telegram бот для уведомлений (telegram_bot.py), парсер бирж обновлён (parser_birges.py), handoff создан (agent_outputs/HANDOFF_2026-04-14.md). Freelancehunt заблокирован — пропускаем. Следующий шаг: отклики на биржах + BrowserAct интеграция.
- **12.04.2026** — n8n восстановлен: Payment Processor Agent + Content Marketing Publisher импортированы и активированы через CLI, Telegram credential обновлён, URL: https://n8n.sec-scanner.pro:5678
- **09.04.2026** — Создан freelance toolkit: FREELANCE_PROFILE.md, FREELANCE_RESPONSES.md, TRACKER_ORDERS.csv, DAILY_CHECKLIST.md, QUICKSTART.md, add_order.py, stats.py, show_templates.py, parser_birges.py (инструкции для работы на биржах FL.ru, Kwork, Freelancehunt)
- **08.04.2026** — outbound_daily_digest.py: --help, --today, --limit, --include-contacted работают без ошибок; cash_autopilot.py: убраны `replied`/`replied_at` из FIELDNAMES (backward-compatible, не нужны в CSV); все тесты пройдены (py_compile, hybrid_day_run, cash_autopilot)
- **03.04.2026 (evening)** — Money-first hardening: cash_autopilot.py усилен для pipeline_gap_proposals (выбор qualified/warm → proposal conversion, персонализированные closing сообщения), backward-compatible валидация replied/replied_at в revenue_kpi_report.py, созданы CASH_AUTOPILOT_SUMMARY_*.json + CASH_AUTOPILOT_PLAYBOOK_*.md, протестировано: py_compile, cash_autopilot.py, hybrid_day_run.py --json --cash-mode --save-report
- **03.04.2026** — Cash-mode finalized: добавлены поля `replied`/`replied_at` в OUTBOUND_72H_TRACKER.csv (backward-compatible fallback приоритет: replied → статус), изменён приоритет bottleneck'ов (proposal_to_pay_low → reply_rate_low → traffic_low → lead_quality_low), добавлен случай pipeline_gap_proposals (qualified есть, proposals нет), tested: `--cash-mode`, `--json`, `--save-report`
- **29.03.2026** — API fixed: nginx proxy updated (8080 → 8000), api_payments.py synced (removed digital product code), lead_scoring.py updated (added `audit_request_submitted` event)
- **29.03.2026** — API health check working: `curl -s https://api.sec-scanner.pro/healthz` → `{"ok":true}`
- **29.03.2026** — Audit request endpoint working: creates leads with UTM tracking
- **29.03.2026** — n8n workflows импортированы: Payment Processor Agent, Content Marketing Publisher
- **29.03.2026** — Telegram credential создан для @sec_scanner_content_bot
- **26.03.2026** — Telegram Bot настроен: Chat ID 280851345
- **31.03.2026** — Синхронизирована командная модель OpenCode + Vibe Kanban + Cursor, регламент зафиксирован: `agent_outputs/team_sync_opencode_vibe_cursor_2026-03-31.md`
- **31.03.2026** — Vibe Kanban: настроен репозиторий `fastapi-project-backend` (branch `main`, backend-only scripts), создан issue `Backend smoke check` и workspace `d0700e6e-58a7-405b-ab74-8697b3e1255b`
- **31.03.2026** — Реализован пакет Revenue Sprint 14d: Vibe board seed, n8n runbook/scripts, outbound kit, digital-offers launch, OpenCode daily routine, KPI templates; отчёт: `agent_outputs/revenue_sprint_implementation_2026-03-31.md`

---

## Следующие шаги

**До денег (обязательно):**
1. Продажи по playbook: минимум 2 proposals, 1 payment_pending
2. Актуальность трекера: править CSV после каждой отправки КП и ответа клиента

**После денег/ИП (инфраструктура):**
1. Оформление ИП → подключение YooKassa → webhook на `/webhook/yookassa-payment`
2. n8n: стабильный N8N_API_KEY через UI + импорт Payment Processor Agent (with Scoring)
3. Активировать лид-магнит и воронку продаж
4. Создать Supabase проект для CRM (после создания — настроить подключение)

---

## Открытые вопросы / риски

- YooKassa — ждёт оформления ИП
- Supabase — проект не создан в облаке
- n8n — нужен стабильный N8N_API_KEY + импорт Payment Processor Agent

## Code improvements (второй приоритет)

- Единый вечерний отчёт: свести в одну строку факт `proposals / payment_pending / won / revenue_rub`
- Опционально: расширить автопилот под несколько очередей (freelance_* vs telegram_*)

---

## SSH Access

```
ssh -p 22222 root@85.239.38.163
```

Details: [`docs/SERVER_SSH_ACCESS.md`](docs/SERVER_SSH_ACCESS.md)

---

## Где искать отчёты по завершённым крупным задачам

- `docs/REPORT_*` или `docs/*_SETUP.md`
- `agent_outputs/` (в т.ч. code review по правилу Multi-Agent)
