#!/usr/bin/env python3
"""
Добавляет новый заказ в TRACKER_ORDERS.csv.

Запуск:
    python freelance/add_order.py

Интерактивный ввод:
    - Платформа (FL.ru, Kwork, Freelancehunt)
    - ID заказа
    - Имя клиента
    - Название задачи
    - Цена
    - Заметки
"""

import csv
from datetime import date
from pathlib import Path


def main():
    tracker_file = Path(__file__).parent / "TRACKER_ORDERS.csv"

    print("=" * 60)
    print("ДОБАВЛЕНИЕ НОВОГО ЗАКАЗА В ТРЕКЕР")
    print("=" * 60)
    print()

    print("Платформа:")
    print("  1. FL.ru")
    print("  2. Kwork")
    print("  3. Freelancehunt")
    print()

    platform_choice = input("Выбери номер (1-3): ").strip()
    platforms = {"1": "FL.ru", "2": "Kwork", "3": "Freelancehunt"}
    platform = platforms.get(platform_choice, "unknown")

    if platform == "unknown":
        print("Неверный выбор.")
        return 1

    order_id = input("ID заказа (например, 12345): ").strip()
    client_name = input("Имя клиента: ").strip()
    order_title = input("Название задачи: ").strip()
    price_str = input("Цена (₽): ").strip()
    notes = input("Заметки: ").strip()

    try:
        price = int(float(price_str)) if price_str else 0
    except ValueError:
        price = 0

    today = date.today().isoformat()

    row = {
        "date": today,
        "platform": platform,
        "order_id": order_id,
        "client_name": client_name,
        "order_title": order_title,
        "status": "new",
        "price_rub": str(price),
        "response_date": "",
        "start_date": "",
        "deadline": "",
        "completed_date": "",
        "notes": notes,
    }

    with tracker_file.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if tracker_file.stat().st_size == 0:
            writer.writeheader()
        writer.writerow(row)

    print()
    print("=" * 60)
    print("✅ Заказ добавлен!")
    print(f"   Платформа: {platform}")
    print(f"   Клиент: {client_name}")
    print(f"   Задача: {order_title}")
    print(f"   Цена: {price:,} ₽")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
