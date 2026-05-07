# Пересборка Frontend Docker

## Статус
- **Дата:** 2026-05-07
- **Изменения:** Новый дизайн магазина в стиле VPN (dark theme, gradient borders, glow effects, feature cards)

## Что изменилось
- `services/frontend/src/pages/store.astro` — полностью переработан дизайн
- Добавлена интеграция с Telegram Theme (tg.themeParams)
- Новые стили: градиентные рамки, свечение карточек, анимации

## Как пересобрать

```bash
# На VPS
cd /root
docker build -t sec-scanner-frontend services/frontend
docker stop sec-scanner-frontend-1
docker rm sec-scanner-frontend-1
docker run -d --name sec-scanner-frontend-1 -p 127.0.0.1:3000:3000 sec-scanner-frontend npm run preview
```

## Nginx
После поднятия контейнера настроить proxy_pass на 127.0.0.1:3000

## Проблемы
- Docker-образ `sec-scanner-web-check` сейчас используется для фронтенда — нужно заменить на `sec-scanner-frontend`
- Nginx должен проксировать на правильный порт после пересборки
