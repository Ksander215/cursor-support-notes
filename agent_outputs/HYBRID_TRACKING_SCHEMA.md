# Hybrid Tracking Schema

Единый стандарт трекинга лидов из Telegram и фриланс-бирж.

## Обязательные поля (OUTBOUND tracker)

- `lead_source` — `telegram_dm` | `telegram_chat` | `freelance_kwork` | `freelance_flru` | `referral`
- `status` — `new` | `contacted` | `warm` | `qualified` | `hot` | `call/proposal` | `payment_pending` | `won` | `lost`
- `next_step` — конкретное действие (`first_touch`, `follow_up_d1`, `call_or_proposal`, `payment_check`, ...)
- `deal_value_rub` — ожидаемая/фактическая сумма

## Канонический pipeline

`contacted -> qualified -> call/proposal -> payment_pending -> won/lost`

## Правило синхронизации с Vibe Kanban

- `new/contacted/warm` -> `Inbox Leads` / `Qualified`
- `qualified/hot/call/proposal` -> `Call/Proposal`
- `payment_pending` -> `Payment Pending`
- `won` -> `Won`
- `lost` -> `Lost`

## Ежедневная проверка

1. Нет строк без `lead_source`.
2. Нет строк без `status`.
3. Все `payment_pending` имеют `next_step_at`.
4. Все `won` имеют `deal_value_rub` > 0.
