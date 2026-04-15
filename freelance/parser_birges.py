#!/usr/bin/env python3
"""
Парсер новых заказов с фриланс-бирж.

Мониторит FL.ru и Kwork.
Фильтрует по ключевым словам.
Записывает найденные заказы в TRACKER_ORDERS.csv.
Отправляет уведомления в Telegram.

Установка зависимостей:
    pip install httpx beautifulsoup4

Запуск:
    python3 freelance/parser_birges.py

Переменные окружения (.env):
    TELEGRAM_BOT_TOKEN=твой_токен
    TELEGRAM_CHAT_ID=твой_chat_id
"""

from __future__ import annotations

import csv
import os
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

try:
    import httpx
except ImportError:
    print("Установите httpx: pip install httpx")
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("Установите beautifulsoup4: pip install beautifulsoup4")
    sys.exit(1)

TRACKER_FILE = Path(__file__).parent / "TRACKER_ORDERS.csv"
KEYWORDS = [
    "python",
    "api",
    "bot",
    "telegram",
    "automation",
    "парсинг",
    "интеграция",
    "fastapi",
    "backend",
    "скрипт",
]
PLATFORMS_URLS = {
    "fl_ru": "https://www.fl.ru/projects/category/programmirovanie/python/",
    "kwork": "https://kwork.ru/projects?c=41",
}


@dataclass
class FoundOrder:
    platform: str
    title: str
    url: str
    description: str
    price: str
    published: str


def get_telegram_config() -> tuple[str, str]:
    token = os.environ.get("FREELANCE_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("FREELANCE_CHAT_ID", "").strip()
    return token, chat_id


def send_telegram_message(text: str) -> bool:
    token, chat_id = get_telegram_config()
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
            return resp.status_code == 200
    except Exception:
        return False


def parse_fl_ru() -> list[FoundOrder]:
    """Парсит FL.ru. Возвращает список найденных заказов."""
    orders: list[FoundOrder] = []
    url = PLATFORMS_URLS["fl_ru"]
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                print(f"[FL.ru] HTTP {resp.status_code}")
                return orders
            soup = BeautifulSoup(resp.text, "html.parser")
            for item in soup.select(".b-poster-grid__col, .b-poster, [class*='project-item']"):
                title_el = item.select_one("a[href*='/projects/'], h2 a, .b-poster__title a")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                link = title_el.get("href", "")
                if link and not link.startswith("http"):
                    link = "https://www.fl.ru" + link
                desc_el = item.select_one(".b-poster__description, .b-poster__text, p")
                desc = desc_el.get_text(strip=True)[:200] if desc_el else ""
                price_el = item.select_one(".b-poster__price, [class*='price']")
                price = price_el.get_text(strip=True) if price_el else ""
                orders.append(
                    FoundOrder(
                        platform="FL.ru",
                        title=title,
                        url=link,
                        description=desc,
                        price=price,
                        published="",
                    )
                )
    except Exception as e:
        print(f"[FL.ru] Ошибка: {e}")
    return orders


def parse_kwork() -> list[FoundOrder]:
    """Парсит Kwork. Возвращает список найденных заказов."""
    orders: list[FoundOrder] = []
    url = PLATFORMS_URLS["kwork"]
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                print(f"[Kwork] HTTP {resp.status_code}")
                return orders
            soup = BeautifulSoup(resp.text, "html.parser")
            for item in soup.select("[class*='order-item'], [class*='project-item'], .kw-card"):
                title_el = item.select_one("a[class*='title'], h3 a, .kw-card__title a")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                link = title_el.get("href", "")
                if link and not link.startswith("http"):
                    link = "https://kwork.ru" + link
                desc_el = item.select_one(".kw-card__desc, p")
                desc = desc_el.get_text(strip=True)[:200] if desc_el else ""
                price_el = item.select_one("[class*='price'], .kw-card__price")
                price = price_el.get_text(strip=True) if price_el else ""
                orders.append(
                    FoundOrder(
                        platform="Kwork",
                        title=title,
                        url=link,
                        description=desc,
                        price=price,
                        published="",
                    )
                )
    except Exception as e:
        print(f"[Kwork] Ошибка: {e}")
    return orders


def filter_orders(orders: list[FoundOrder], keywords: list[str]) -> list[FoundOrder]:
    """Фильтрует заказы по ключевым словам."""
    filtered = []
    for order in orders:
        text = f"{order.title} {order.description}".lower()
        if any(kw.lower() in text for kw in keywords):
            filtered.append(order)
    return filtered


def save_to_tracker(orders: list[FoundOrder]) -> int:
    """Записывает найденные заказы в TRACKER_ORDERS.csv."""
    if not orders:
        return 0
    today = date.today().isoformat()
    existing_rows: list[dict[str, str]] = []
    if TRACKER_FILE.exists():
        with TRACKER_FILE.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            existing_rows.extend(reader)
    existing_urls = {r.get("url", "") for r in existing_rows if r.get("url")}
    new_rows = []
    for order in orders:
        if order.url in existing_urls:
            continue
        new_rows.append(
            {
                "date": today,
                "platform": order.platform,
                "order_id": order.url.split("/")[-1] if "/" in order.url else "",
                "client_name": "",
                "order_title": order.title[:100],
                "status": "new",
                "price_rub": order.price,
                "response_date": "",
                "start_date": "",
                "deadline": "",
                "completed_date": "",
                "notes": order.description[:200],
                "url": order.url,
            }
        )
    if not new_rows:
        return 0
    fieldnames = list(new_rows[0].keys())
    all_rows = existing_rows + new_rows
    with TRACKER_FILE.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)
    return len(new_rows)


def format_orders_message(orders: list[FoundOrder]) -> str:
    """Форматирует список заказов для Telegram."""
    if not orders:
        return "Новых заказов по ключевым словам не найдено."
    lines = [f"🔍 <b>Найдено заказов: {len(orders)}</b>\n"]
    for i, order in enumerate(orders[:10], 1):
        lines.append(f"<b>{i}. {order.platform}</b>")
        lines.append(f"   📝 {order.title[:80]}")
        if order.price:
            lines.append(f"   💰 {order.price}")
        lines.append(f"   🔗 {order.url}")
        lines.append("")
    if len(orders) > 10:
        lines.append(f"...и ещё {len(orders) - 10} заказов")
    return "\n".join(lines)


def main() -> int:
    parser_args = sys.argv[1:]
    verbose = "--verbose" in parser_args
    no_save = "--no-save" in parser_args

    print("=" * 60)
    print("Парсер фриланс-бирж (FL.ru + Kwork)")
    print("=" * 60)
    print()
    print(f"Ключевые слова: {', '.join(KEYWORDS)}")
    print()

    all_orders: list[FoundOrder] = []

    print("[1/2] Парсинг FL.ru...")
    fl_orders = parse_fl_ru()
    print(f"       Найдено заказов: {len(fl_orders)}")
    all_orders.extend(fl_orders)

    print("[2/2] Парсинг Kwork...")
    kw_orders = parse_kwork()
    print(f"       Найдено заказов: {len(kw_orders)}")
    all_orders.extend(kw_orders)

    print()
    filtered = filter_orders(all_orders, KEYWORDS)
    print(f"Подходит по ключевым словам: {len(filtered)}")
    print()

    if not filtered:
        print("Заказы не найдены. Попробуйте позже или измените ключевые слова.")
        print()
    else:
        for i, order in enumerate(filtered[:20], 1):
            print(f"  {i}. [{order.platform}] {order.title[:60]}")
            if order.price:
                print(f"     Цена: {order.price}")
            print(f"     URL: {order.url}")
            print()

    if not no_save and filtered:
        saved = save_to_tracker(filtered)
        print(f"Сохранено в трекер: {saved} новых заказов")

    token, chat_id = get_telegram_config()
    if token and chat_id and filtered:
        msg = format_orders_message(filtered)
        if send_telegram_message(msg):
            print("Уведомление отправлено в Telegram")
        else:
            print("Не удалось отправить уведомление в Telegram")

    print()
    print("=" * 60)
    print("Ручной мониторинг (альтернатива):")
    print()
    print("FL.ru:")
    print("  1. Открой: https://www.fl.ru/projects/category/programmirovanie/python/")
    print("  2. Фильтр: Python, API, Telegram")
    print("  3. Сортировка: По дате")
    print("  4. Откликнись на 5-10 заказов")
    print()
    print("Kwork:")
    print("  1. Открой: https://kwork.ru/projects?c=41")
    print("  2. Фильтр: Программирование")
    print("  3. Сортировка: Новые")
    print("  4. Откликнись на 3-5 заказов")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
