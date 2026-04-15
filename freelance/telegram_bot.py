#!/usr/bin/env python3
"""
Telegram бот для уведомлений о новых заказах на фриланс-биржах.

Отправляет напоминания о:
- Нужно откликнуться на заказы (утром)
- Статус трекера (вечером)
- Конверсия откликов

Настройка:
    1. Создай бота через @BotFather в Telegram
    2. Получи токен бота
    3. Получи свой chat_id (напиши боту /start, затем проверь API)
    4. Установи переменные окружения:

Установка зависимостей:
    pip install httpx python-telegram-bot

Запуск:
    python3 freelance/telegram_bot.py

Переменные окружения (.env):
    FREELANCE_BOT_TOKEN=твой_токен_бота
    FREELANCE_CHAT_ID=твой_chat_id
"""

from __future__ import annotations

import csv
import os
import sys
from datetime import date
from pathlib import Path

try:
    import httpx
except ImportError:
    print("Установите httpx: pip install httpx")
    sys.exit(1)

TRACKER_FILE = Path(__file__).parent / "TRACKER_ORDERS.csv"
TELEGRAM_API = "https://api.telegram.org"


def get_bot_token() -> str:
    token = os.environ.get("FREELANCE_BOT_TOKEN", "").strip()
    if not token:
        print("Ошибка: установите FREELANCE_BOT_TOKEN в .env")
        print("1. Создай бота через @BotFather в Telegram")
        print("2. Получи токен бота")
        print("3. Установи: export FREELANCE_BOT_TOKEN=твой_токен")
        sys.exit(1)
    return token


def get_chat_id() -> str:
    chat_id = os.environ.get("FREELANCE_CHAT_ID", "").strip()
    if not chat_id:
        print("Ошибка: установите FREELANCE_CHAT_ID в .env")
        print("1. Напиши боту /start в Telegram")
        print("2. Проверь chat_id через API: https://api.telegram.org/bot<token>/getUpdates")
        print("3. Установи: export FREELANCE_CHAT_ID=твой_chat_id")
        sys.exit(1)
    return chat_id


def send_telegram_message(text: str) -> bool:
    token = get_bot_token()
    chat_id = get_chat_id()
    url = f"{TELEGRAM_API}/bot{token}/sendMessage"

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                },
            )
            if response.status_code == 200:
                print("Сообщение отправлено в Telegram")
                return True
            else:
                print(f"Ошибка отправки: {response.status_code} {response.text}")
                return False
    except Exception as e:
        print(f"Ошибка подключения к Telegram: {e}")
        return False


def load_tracker() -> list[dict[str, str]]:
    if not TRACKER_FILE.exists():
        return []
    rows = []
    with TRACKER_FILE.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(dict(row))
    return rows


def get_daily_stats(rows: list[dict[str, str]]) -> dict[str, int]:
    today = date.today().isoformat()
    today_rows = [r for r in rows if r.get("date", "") == today]

    total = len(today_rows)
    responded = sum(
        1 for r in today_rows if r.get("status", "") in ("responded", "in_progress", "completed")
    )
    completed = sum(1 for r in today_rows if r.get("status", "") == "completed")
    new = sum(1 for r in today_rows if r.get("status", "") == "new")

    revenue = 0
    for r in today_rows:
        try:
            price = int(float(r.get("price_rub", "0")))
            if r.get("status", "") == "completed":
                revenue += price
        except (ValueError, TypeError):
            pass

    return {
        "total": total,
        "responded": responded,
        "completed": completed,
        "new": new,
        "revenue": revenue,
    }


def format_morning_message() -> str:
    today = date.today().isoformat()
    msg = [
        "☀️ <b>Доброе утро!</b>",
        f"📅 Дата: {today}",
        "",
        "<b>Задача на сегодня:</b>",
        "• Откликнуться на 5-10 заказов на FL.ru",
        "• Откликнуться на 3-5 заказов на Kwork",
        "• Обновить трекер после каждого отклика",
        "",
        "<b>Шаблоны откликов:</b>",
        "cat freelance/FREELANCE_RESPONSES.md",
        "",
        "<b>Трекер:</b>",
        "python3 freelance/add_order.py",
    ]
    return "\n".join(msg)


def format_evening_message(rows: list[dict[str, str]]) -> str:
    stats = get_daily_stats(rows)
    today = date.today().isoformat()

    msg = [
        "🌙 <b>Итоги дня</b>",
        f"📅 Дата: {today}",
        "",
        "📊 <b>Статистика:</b>",
        f"• Откликов сегодня: {stats['total']}",
        f"• Ответов: {stats['responded']}",
        f"• Завершено: {stats['completed']}",
        f"• Ожидают ответа: {stats['new']}",
        f"• Заработано: {stats['revenue']:,} ₽",
        "",
    ]

    if stats["total"] > 0:
        conv_responded = (stats["responded"] / stats["total"]) * 100
        msg.append("📈 <b>Конверсия:</b>")
        msg.append(f"• Отклик → Ответ: {conv_responded:.1f}%")

    if stats["new"] > 0:
        msg.append("")
        msg.append(f"⏳ <b>Ожидают ответа:</b> {stats['new']}")
        msg.append("   Проверь сообщения на биржах!")

    msg.append("")
    msg.append("💡 <b>Совет:</b>")
    if stats["total"] < 5:
        msg.append("   Цель: минимум 5 откликов в день!")
    else:
        msg.append("   Отлично! Продолжай в том же духе!")

    return "\n".join(msg)


def format_stats_message(rows: list[dict[str, str]]) -> str:
    stats = get_daily_stats(rows)
    total_rows = len(rows)

    all_responded = sum(
        1 for r in rows if r.get("status", "") in ("responded", "in_progress", "completed")
    )
    all_completed = sum(1 for r in rows if r.get("status", "") == "completed")
    all_revenue = 0
    for r in rows:
        try:
            price = int(float(r.get("price_rub", "0")))
            if r.get("status", "") == "completed":
                all_revenue += price
        except (ValueError, TypeError):
            pass

    msg = [
        "📊 <b>Общая статистика</b>",
        "",
        "📊 <b>За всё время:</b>",
        f"• Всего откликов: {total_rows}",
        f"• Ответов: {all_responded}",
        f"• Завершено: {all_completed}",
        f"• Заработано: {all_revenue:,} ₽",
        "",
    ]

    if total_rows > 0:
        conv = (all_responded / total_rows) * 100
        msg.append("📈 <b>Общая конверсия:</b>")
        msg.append(f"• Отклик → Ответ: {conv:.1f}%")

    if all_completed > 0:
        avg_price = all_revenue // all_completed
        msg.append(f"• Средний чек: {avg_price:,} ₽")

    return "\n".join(msg)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Telegram бот для уведомлений о фриланс-заказах.")
    parser.add_argument("--morning", action="store_true", help="Отправить утреннее напоминание")
    parser.add_argument("--evening", action="store_true", help="Отправить вечерний отчёт")
    parser.add_argument("--stats", action="store_true", help="Отправить общую статистику")
    parser.add_argument("--setup", action="store_true", help="Показать инструкции по настройке")
    args = parser.parse_args()

    if args.setup:
        print("=" * 60)
        print("НАСТРОЙКА TELEGRAM БОТА")
        print("=" * 60)
        print()
        print("1. Создай бота через @BotFather в Telegram:")
        print("   - Открой @BotFather в Telegram")
        print("   - Напиши /newbot")
        print("   - Введи имя бота: Freelance Tracker")
        print("   - Введи username: your_name_freelance_bot")
        print("   - Скопируй токен бота")
        print()
        print("2. Получи свой chat_id:")
        print("   - Напиши боту /start")
        print("   - Открой: https://api.telegram.org/bot<TOKEN>/getUpdates")
        print("   - Найди chat_id в ответе")
        print()
        print("3. Установи переменные окружения:")
        print("   export FREELANCE_BOT_TOKEN=твой_токен_бота")
        print("   export FREELANCE_CHAT_ID=твой_chat_id")
        print()
        print("4. Запусти бота:")
        print("   python3 freelance/telegram_bot.py --morning")
        print("   python3 freelance/telegram_bot.py --evening")
        print("   python3 freelance/telegram_bot.py --stats")
        print()
        print("5. Настрой крон (автоматические уведомления):")
        print("   crontab -e")
        print(
            "   0 9 * * 1-5 cd /home/alex/fastapi-project && python3 freelance/telegram_bot.py --morning"
        )
        print(
            "   0 20 * * 1-5 cd /home/alex/fastapi-project && python3 freelance/telegram_bot.py --evening"
        )
        print("=" * 60)
        return 0

    rows = load_tracker()

    if args.morning:
        message = format_morning_message()
        send_telegram_message(message)
        return 0

    if args.evening:
        message = format_evening_message(rows)
        send_telegram_message(message)
        return 0

    if args.stats:
        message = format_stats_message(rows)
        send_telegram_message(message)
        return 0

    print("Используй один из флагов:")
    print("  --morning   Утреннее напоминание")
    print("  --evening   Вечерний отчёт")
    print("  --stats     Общая статистика")
    print("  --setup     Инструкции по настройке")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
