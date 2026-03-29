# MAIN_AGENT — журнал статуса (Cursor / OpenCode)

Использование: *«Прочитай MAIN_AGENT.md и продолжай с последнего места»* — восстанавливает контекст между сессиями. Детальный индекс: [`AGENTS.md`](AGENTS.md).

Обновляйте этот файл при **handoff** между инструментами или людьми: кратко, по пунктам.

**Делегирование OpenCode:** полный шаблон промпта — [.cursor/skills/opencode-project-skills/SKILL.md](.cursor/skills/opencode-project-skills/SKILL.md) (*Делегирование из Cursor*). Cursor может оставаться оркестратором; объём — в OpenCode.

---

## Пакет для OpenCode (копипаст)

*Заполняйте перед передачей задачи в OpenCode; после выполнения — краткий итог в «Последние решения».*

**Цель:**

**Контекст (файлы, эндпоинты, доки):**

**Ограничения (не трогать / обязательные команды):**

**Критерии готовности (что считать «сделано»):**

**Промпт (вставить в OpenCode как есть или доработать):**

```
(пусто — вставить сюда)
```

---

## Сейчас в работе

- **Задача:** Lead Scoring workflows — завершено
- **Ведущий:** OpenCode
- **Ветка / PR:** main (commit d0356d5)

---

## Последние решения

- **29.03.2026** — n8n workflows импортированы: Payment Processor Agent (ID: 2GZcbIjIJpemBEvU), Content Marketing Publisher (ID: upGrgHOtTeDUooqv)
- **29.03.2026** — Telegram credential создан (ID: YwNoa4WrBHZIsLsu), переменные окружения настроены
- **29.03.2026** — Новый n8n API key, docker-compose.n8n.yml обновлён
- **26.03.2026** — Telegram Bot настроен: токен добавлен в .env, Chat ID получен (280851345), бот отправляет тестовые сообщения
- **26.03.2026** — Phase 2 завершён: n8n с PostgreSQL, 25 воркфлоу импортированы (17 активны)
- **25.03.2026** — GitHub remote подключён, коммит с docker-compose.n8n.yml

---

## Следующие шаги

1. Оформление ИП → подключение YooKassa → webhook на `/webhook/yookassa-payment`
2. Активировать лид-магнит и воронку продаж после ИП
3. Создать Supabase проект для CRM (после создания — настроить подключение)

---

## Открытые вопросы / риски

- YooKassa — ждёт оформления ИП
- Supabase — проект не создан в облаке

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
