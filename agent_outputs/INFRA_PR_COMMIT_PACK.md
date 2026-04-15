# Infra PR/Commit Pack (Alembic + Nginx)

Цель: зафиксировать инфраструктурные риски одним проходом, без лишних изменений.

## Scope

- Alembic migration chain consistency.
- Nginx/API localhost port consistency (`8000` vs `8080`).
- n8n API key lifecycle note (без коммита секретов).

## Include in PR

1. `alembic/versions/*.py` только если:
   - исправляли `revision/down_revision`,
   - устраняли конфликт веток,
   - добавляли отсутствующую миграцию.
2. `deploy/nginx/sec-scanner.conf.template` если приводили `proxy_pass` к целевому порту.
3. `scripts/*.sh` только те, где выровнен health check порт.
4. `agent_outputs/infra_guardrails_report.md` как артефакт проверки.

## Exclude from PR

- Любые ключи/токены (`.env`, `.cursor/mcp.json`, credentials).
- Несвязанные бизнес-правки.
- Файлы без отношения к миграциям/портам.

## Pre-PR verification commands

```bash
python scripts/infra_guardrails_report.py
python scripts/test_revenue_webhooks.py --mode all
```

Если окружение готово:

```bash
alembic heads
alembic history --verbose
```

## PR title candidates

- `fix infra drift: align alembic chain and nginx api port`
- `stabilize revenue infra: migrations chain + proxy port consistency`

## Commit message template

```text
Fix infra consistency for revenue pipeline.

- align Alembic migration chain to single head
- remove nginx/api localhost port drift in deployment configs
- add guardrails report and repeatable verification steps
```

## Exit criteria

- `alembic` chain has one head.
- `proxy_pass` and script health checks use one canonical API port.
- Webhook smoke tests return only 2xx.
