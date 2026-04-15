# Follow-up Playbook (Auto)

- Date: `2026-04-08`
- Tasks total: `12`
- Overdue: `10` | Due D+1: `0` | Due D+2: `0` | Missing schedule: `0`

## Execution Order

1. Overdue leads
2. D+2 follow-ups (closing intent)
3. D+1 follow-ups (value-first)
4. Missing schedule cleanup

## Top 10 Follow-ups

- 1. `dev_4` (status=hot, reason=due_today, score=94) -> `call_or_proposal_push`
- 2. `dev_8` (status=hot, reason=due_today, score=90) -> `call_or_proposal_push`
- 3. `dev_10` (status=new, reason=overdue, score=62) -> `followup_overdue_urgent`
- 4. `dev_13` (status=new, reason=overdue, score=62) -> `followup_overdue_urgent`
- 5. `icp_cto_1` (status=new, reason=overdue, score=61) -> `followup_overdue_urgent`
- 6. `icp_cto_2` (status=new, reason=overdue, score=61) -> `followup_overdue_urgent`
- 7. `dev_15` (status=warm, reason=overdue, score=58) -> `followup_overdue_urgent`
- 8. `icp_freelance_1` (status=new, reason=overdue, score=56) -> `followup_overdue_urgent`
- 9. `dev_5` (status=new, reason=overdue, score=56) -> `followup_overdue_urgent`
- 10. `dev_7` (status=new, reason=overdue, score=56) -> `followup_overdue_urgent`

## Message Keys

- `followup_d1_value_first`: короткая польза + мягкий CTA
- `followup_d2_closing`: дедлайн + слот + вопрос на подтверждение
- `followup_overdue_urgent`: reactivation с ограничением по времени
- `call_or_proposal_push`: предложение звонка/КП в тот же день
- `followup_standard`: нейтральный follow-up
- `first_touch_or_reengagement`: первичное касание или re-engage
