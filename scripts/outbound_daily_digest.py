#!/usr/bin/env python3
"""
Ежедневный дайджест: кому написать сегодня по OUTBOUND_72H_TRACKER.csv.

Читает CSV, отбирает строки с next_step_at <= сегодня и статусом warm/hot
(опционально + contacted), сортирует по срочности, печатает готовые тексты.

Опционально дублирует сводку в Telegram, если заданы переменные окружения:
  TELEGRAM_BOT_TOKEN
  TELEGRAM_OUTBOUND_CHAT_ID

Расписание (WSL, каждый будний день в 09:30):
  crontab -e
  30 9 * * 1-5 cd /home/alex/fastapi-project && .venv/bin/python scripts/outbound_daily_digest.py

Windows → Планировщик задач, действие: wsl.exe с аргументами
  -e bash -lc 'cd /home/alex/fastapi-project && .venv/bin/python scripts/outbound_daily_digest.py'
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _default_csv_path() -> Path:
    return _repo_root() / "agent_outputs" / "OUTBOUND_72H_TRACKER.csv"


def _parse_step_date(value: str) -> date | None:
    raw = value.strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _platform_hint(lead_source: str) -> str:
    mapping = {
        "freelance_flru": "FL.ru",
        "freelance_kwork": "Kwork",
        "telegram_chat": "Telegram",
        "telegram_dm": "Telegram",
        "referral": "Реферал (канал — где реально общаетесь; подсказка в notes)",
    }
    return mapping.get(lead_source.strip(), lead_source or "—")


def _message_body(offer: str) -> str:
    bundle = " (Bundle)" if "bundle" in offer.lower() else ""
    return (
        f"Привет! Готов отправить КП по вашему проекту{bundle}. "
        "Предлагаю созвон 10 минут для уточнения деталей, после чего сразу направлю "
        "КП с дедлайном на 24 часа. Удобно закрыть вопросы сегодня?"
    )


@dataclass(frozen=True)
class LeadRow:
    contact_name: str
    lead_source: str
    pain_point: str
    budget_rub: str
    urgency_days: int
    status: str
    next_step: str
    next_step_at: date | None
    offer: str
    notes: str

    def due_today_or_overdue(self, today: date) -> bool:
        if self.next_step_at is None:
            return False
        return self.next_step_at <= today

    def allowed_status(self, include_contacted: bool) -> bool:
        s = self.status.strip().lower()
        if s in {"warm", "hot"}:
            return True
        if include_contacted and s == "contacted":
            return True
        return False


def load_leads(path: Path) -> list[LeadRow]:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows: list[LeadRow] = []
        for r in reader:
            if not r.get("contact_name"):
                continue
            ud = r.get("urgency_days", "").strip()
            try:
                urgency = int(ud) if ud else 999
            except ValueError:
                urgency = 999
            rows.append(
                LeadRow(
                    contact_name=r.get("contact_name", "").strip(),
                    lead_source=r.get("lead_source", "").strip(),
                    pain_point=(r.get("pain_point") or "").strip(),
                    budget_rub=(r.get("budget_rub") or "").strip(),
                    urgency_days=urgency,
                    status=(r.get("status") or "").strip(),
                    next_step=(r.get("next_step") or "").strip(),
                    next_step_at=_parse_step_date(r.get("next_step_at") or ""),
                    offer=(r.get("offer") or "").strip(),
                    notes=(r.get("notes") or "").strip(),
                )
            )
    return rows


def pick_leads(
    rows: list[LeadRow],
    today: date,
    *,
    limit: int,
    include_contacted: bool,
) -> list[LeadRow]:
    picked = [
        r for r in rows if r.due_today_or_overdue(today) and r.allowed_status(include_contacted)
    ]
    picked.sort(key=lambda r: (r.urgency_days, r.next_step_at or date.max))
    return picked[:limit]


def format_card(le: LeadRow, index: int) -> str:
    lines = [
        f"--- #{index} {le.contact_name} ---",
        f"Площадка: {_platform_hint(le.lead_source)}  (lead_source={le.lead_source})",
        f"Статус: {le.status} | offer: {le.offer}",
        f"Срочность (дней): {le.urgency_days} | next_step: {le.next_step} | до: {le.next_step_at}",
        f"Боль: {le.pain_point}" if le.pain_point else "Боль: —",
        f"Заметки: {le.notes}" if le.notes else "Заметки: —",
        "",
        "Текст:",
        _message_body(le.offer),
        "",
    ]
    return "\n".join(lines)


def send_telegram_digest(text: str, *, dry_run: bool) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_OUTBOUND_CHAT_ID", "").strip()
    if not token or not chat:
        return
    if dry_run:
        print("\n[--dry-run] Telegram: пропуск отправки.", file=sys.stderr)
        return
    try:
        import httpx
    except ImportError:
        print("httpx не установлен; установите зависимости проекта.", file=sys.stderr)
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(url, json={"chat_id": chat, "text": text})
    if resp.status_code >= 400:
        print(f"Telegram API: {resp.status_code} {resp.text}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Дайджест outbound: кому написать сегодня (см. docstring для cron).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=_default_csv_path(),
        help=f"Путь к CSV (по умолчанию: {_default_csv_path()})",
    )
    parser.add_argument(
        "--limit", type=int, default=2, help="Сколько лидов показать (по умолчанию 2)"
    )
    parser.add_argument(
        "--include-contacted",
        action="store_true",
        help="Включить status=contacted, если next_step_at уже наступил",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Не отправлять в Telegram даже при заданных токенах",
    )
    parser.add_argument(
        "--today",
        type=str,
        default="",
        help="Дата «сегодня» YYYY-MM-DD (для тестов; по умолчанию системная)",
    )
    args = parser.parse_args()

    csv_path: Path = args.csv
    if not csv_path.is_file():
        print(f"Файл не найден: {csv_path}", file=sys.stderr)
        return 1

    if args.today:
        try:
            today = date.fromisoformat(args.today.strip())
        except ValueError:
            print("Некорректный --today, ожидается YYYY-MM-DD", file=sys.stderr)
            return 1
    else:
        today = date.today()

    rows = load_leads(csv_path)
    picked = pick_leads(
        rows, today, limit=max(1, args.limit), include_contacted=args.include_contacted
    )

    header = (
        f"Outbound digest на {today.isoformat()} (лимит {args.limit}, "
        f"contacted={'да' if args.include_contacted else 'нет'})\n"
        f"Источник: {csv_path}\n"
    )
    if not picked:
        body = (
            "Нет лидов по критериям (warm/hot"
            + (", contacted" if args.include_contacted else "")
            + ") с next_step_at <= сегодня.\n"
        )
        print(header + body)
        send_telegram_digest(header + body, dry_run=args.dry_run)
        return 0

    parts = [header]
    for i, le in enumerate(picked, start=1):
        parts.append(format_card(le, i))
    full_text = "\n".join(parts).strip() + "\n"
    print(full_text)
    send_telegram_digest(full_text, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
