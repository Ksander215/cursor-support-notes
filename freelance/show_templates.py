#!/usr/bin/env python3
"""
Показывает шаблоны откликов для быстрого копирования.

Запуск:
    python freelance/show_templates.py

Использование:
    Выбери номер шаблона → скопируй → адаптируй под заказ
"""

from pathlib import Path


def main():
    templates_file = Path(__file__).parent / "FREELANCE_RESPONSES.md"

    if not templates_file.exists():
        print(f"Файл не найден: {templates_file}")
        return 1

    content = templates_file.read_text(encoding="utf-8")

    templates = []
    current_template = []
    current_title = ""

    for line in content.split("\n"):
        if line.startswith("## Шаблон") or line.startswith("## Короткие"):
            if current_template and current_title:
                templates.append((current_title, "\n".join(current_template)))
            current_title = line.replace("## ", "")
            current_template = [line]
        elif current_title:
            current_template.append(line)

    if current_template and current_title:
        templates.append((current_title, "\n".join(current_template)))

    print("=" * 70)
    print("ШАБЛОНЫ ОТЛИКОВ ДЛЯ БИРЖ")
    print("=" * 70)
    print()

    for i, (title, _) in enumerate(templates, 1):
        print(f"{i}. {title}")

    print()
    print("=" * 70)
    print("Выбери номер шаблона (или 'q' для выхода):")
    print("=" * 70)

    while True:
        choice = input("> ").strip()

        if choice.lower() == "q":
            print("До свидания!")
            return 0

        try:
            index = int(choice) - 1
            if 0 <= index < len(templates):
                title, text = templates[index]
                print("\n" + "=" * 70)
                print(f"ШАБЛОН: {title}")
                print("=" * 70)
                print()
                print(text)
                print()
                print("=" * 70)
                print("Скопируй текст выше и адаптируй под заказ")
                print("=" * 70)
            else:
                print(f"Неверный номер. Введи число от 1 до {len(templates)}")
        except ValueError:
            print("Введи число или 'q' для выхода")


if __name__ == "__main__":
    raise SystemExit(main())
