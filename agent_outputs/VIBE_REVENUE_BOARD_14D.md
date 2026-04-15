# Vibe Kanban: Revenue Sprint 14d (white-only)

Дата старта: `2026-03-31`

## Board setup

- Board name: `Revenue Sprint 14d`
- Owner: `alex`
- Policy: `white_only`
- WIP limit global: `3` активные сделки
- SLA first response: `15 min`
- Review cadence: ежедневный standup `10:00`, вечерний review `19:30`

## Columns

1. `Inbox Leads`
2. `Qualified`
3. `Call/Proposal`
4. `Payment Pending`
5. `Delivery/Follow-up`
6. `Won`
7. `Lost`

## Swimlanes

- `Services Cashflow` — экспресс-аудит, ручной аудит, консалтинг
- `Digital Sales Ops` — PDF, CI/CD templates, авто-доставка, email sequence

## Card definition template

Используйте этот шаблон в описании карточки:

```md
### ICP
- Role:
- Stack:
- Budget band:
- Urgency:

### Offer
- Product/service:
- Price:
- Time-to-value:

### Next step
- Action owner:
- Deadline:
- Success condition:

### Compliance
- [ ] Только легальные платежные каналы
- [ ] Нет серых схем/обходов
- [ ] Условия услуги зафиксированы в переписке
```

## Done criteria (карточка сделки)

- Клиент получил финальный deliverable (аудит/PDF/шаблоны)
- Получено подтверждение оплаты
- Отправлен follow-up (D+1, D+3, D+7)
- Зафиксированы метрики в scorecard

## Priority matrix

- `P0`: горячие лиды с дедлайном <= 48 часов
- `P1`: квалифицированные лиды с подтвержденным бюджетом
- `P2`: warm leads для nurturing

## Daily workflow

1. `09:45` — triage новых лидов.
2. `10:00` — назначить максимум 3 активных сделки.
3. `13:00` — follow-up по `Payment Pending`.
4. `16:00` — публикация/дистрибуция офферов.
5. `19:30` — обновить KPI и перенос карточек.

## Required linked assets

- `agent_outputs/VIBE_REVENUE_CARDS_SEED_14D.csv`
- `agent_outputs/OUTBOUND_72H_EXECUTION.md`
- `docs/N8N_REVENUE_RUNBOOK_14D.md`
- `agent_outputs/REVENUE_OPTIMIZATION_SCORECARD.csv`
