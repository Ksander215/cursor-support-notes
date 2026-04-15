# IP + YooKassa Transition Checklist (Hybrid)

Статус: подготовка к переключению оплаты на сайт.

## 1) Юридическая готовность

- [ ] ИП зарегистрирован
- [ ] УСН 6% подтверждена
- [ ] Реквизиты для публичной оферты готовы

## 2) Платежная готовность

- [ ] YooKassa верифицирована
- [ ] `YOOKASSA_SHOP_ID` и `YOOKASSA_SECRET_KEY` внесены в окружение
- [ ] Webhook `payment.succeeded` настроен
- [ ] Webhook `payment.canceled` настроен
- [ ] Health-check `GET /payments/yookassa/health` возвращает configured=true

## 3) Воронка после switch

- [ ] В исходящих сообщениях CTA меняется на сайт checkout
- [ ] В tracker поле `notes` содержит `yookassa_checkout`
- [ ] Ручной fallback сохранён на случай сбоя

## 4) n8n readiness

- [ ] Workflow оплаты активен
- [ ] Workflow доставки активен
- [ ] Workflow follow-up активен
- [ ] Smoke webhooks проходят

## 5) Условие завершения

- [ ] Минимум 5 успешных оплат через checkout подряд
- [ ] Нулевая потеря лидов в `payment_pending`
- [ ] Переход на `IP_Ready` режим включён по умолчанию

## Ссылки

- [docs/QUICK_START_IP.md](docs/QUICK_START_IP.md)
- [docs/MONETIZATION_CHOICE.md](docs/MONETIZATION_CHOICE.md)
- [docs/IP_YOOKASSA_SWITCH_RUNBOOK.md](docs/IP_YOOKASSA_SWITCH_RUNBOOK.md)
