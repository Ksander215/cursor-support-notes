# OpenCode Prompt: Infra Hardening Pass

```text
Репозиторий: sec-scanner.pro (fastapi-project)

Сначала прочитай:
- AGENTS.md
- MAIN_AGENT.md
- agent_outputs/INFRA_PR_COMMIT_PACK.md

Задача:
Сделать точечный infra hardening pass по Alembic + Nginx API port consistency.

Обязательные шаги:
1) Проверить цепочку миграций Alembic:
   - один root, один head
   - нет broken down_revision ссылок
2) Проверить drift портов API в:
   - deploy/nginx/sec-scanner.conf.template
   - scripts/*.sh
3) Если найден drift, привести к одному каноническому порту (без изменения бизнес-логики).
4) Сгенерировать и обновить отчет:
   - python scripts/infra_guardrails_report.py
5) Прогнать smoke:
   - python scripts/test_revenue_webhooks.py --mode all

Ограничения:
- Не коммитить секреты/ключи.
- Не трогать plan-файл.
- Не изменять несвязанные модули.

Формат результата:
- Краткий отчёт: что изменено, почему, какие проверки выполнены, что осталось.
```
