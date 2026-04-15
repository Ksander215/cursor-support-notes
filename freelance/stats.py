#!/usr/bin/env python3
"""
Подсчёт статистики из TRACKER_ORDERS.csv.

Запуск:
    python freelance/stats.py

Выводит:
    - Общее количество заказов
    - Конверсия (отклики → ответы → заказы)
    - Средний чек
    - Заработок
"""

import csv
from collections import Counter
from pathlib import Path


def main():
    tracker_file = Path(__file__).parent / "TRACKER_ORDERS.csv"

    if not tracker_file.exists():
        print(f"Файл не найден: {tracker_file}")
        print("Сначала добавь заказы в трекер.")
        return 1

    rows = []
    with tracker_file.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    if not rows:
        print("Трекер пуст. Добавь первый заказ.")
        return 1

    total_opens = len(rows)
    status_counts = Counter(row.get("status", "new") for row in rows)

    responded = sum(
        1 for row in rows if row.get("status", "new") in ["responded", "in_progress", "completed"]
    )
    in_progress = sum(1 for row in rows if row.get("status", "new") == "in_progress")
    completed = sum(1 for row in rows if row.get("status", "new") == "completed")
    cancelled = sum(1 for row in rows if row.get("status", "new") == "cancelled")

    prices = []
    for row in rows:
        price_str = row.get("price_rub", "0").strip()
        try:
            price = int(float(price_str)) if price_str else 0
            if price > 0:
                prices.append(price)
        except ValueError:
            pass

    total_revenue = sum(prices)
    avg_price = total_revenue / len(prices) if prices else 0

    print("=" * 60)
    print("СТАТИСТИКА ФРИЛАНСА")
    print("=" * 60)
    print()

    print("📊 ОБЩАЯ СТАТИСТИКА:")
    print(f"   Всего откликов: {total_opens}")
    print(f"   Ответов: {responded} ({responded / total_opens * 100:.1f}%)")
    print(f"   В работе: {in_progress}")
    print(f"   Завершено: {completed}")
    print(f"   Отменено: {cancelled}")
    print()

    print("💰 ФИНАНСЫ:")
    print(f"   Заработано: {total_revenue:,} ₽")
    if prices:
        print(f"   Средний чек: {avg_price:,.0f} ₽")
        print(f"   Мин. чек: {min(prices):,} ₽")
        print(f"   Макс. чек: {max(prices):,} ₽")
    print()

    print("📈 КОНВЕРСИЯ:")
    conversion_opens_to_responses = (responded / total_opens * 100) if total_opens > 0 else 0
    conversion_responses_to_orders = (completed / responded * 100) if responded > 0 else 0
    conversion_total = (completed / total_opens * 100) if total_opens > 0 else 0

    print(f"   Отклик → Ответ: {conversion_opens_to_responses:.1f}%")
    print(f"   Ответ → Заказ: {conversion_responses_to_orders:.1f}%")
    print(f"   Отклик → Заказ: {conversion_total:.1f}%")
    print()

    platforms = Counter(row.get("platform", "unknown") for row in rows)
    print("🏷️ ПО ПЛАТФОРМАМ:")
    for platform, count in platforms.most_common():
        print(f"   {platform}: {count} откликов")
    print()

    print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
