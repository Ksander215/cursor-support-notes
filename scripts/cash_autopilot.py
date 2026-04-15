#!/usr/bin/env python3
"""Cash autopilot for daily revenue-focused execution.

Flow:
1) Run hybrid day pipeline in cash-mode and parse JSON summary.
2) Build top closing queue from tracker.
3) Generate ready-to-send DM/call scripts.
4) Save artifacts in agent_outputs.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

TRACKER_DEFAULT = Path("agent_outputs/OUTBOUND_72H_TRACKER.csv")
OUT_DIR_DEFAULT = Path("agent_outputs")
HYBRID_RUN_SCRIPT = Path("scripts/hybrid_day_run.py")

FIELDNAMES = [
    "timestamp",
    "lead_source",
    "contact_name",
    "project_type",
    "pain_point",
    "budget_rub",
    "urgency_days",
    "status",
    "next_step",
    "next_step_at",
    "offer",
    "deal_value_rub",
    "notes",
]


def get_replied(row: dict[str, str]) -> bool:
    """Check iflead replied (backward-compatible)."""
    replied_val = row.get("replied", "").strip().lower()
    if replied_val in ("true", "1", "yes"):
        return True
    if replied_val in ("false", "0", "no"):
        return False
    return row.get("status", "").lower() in {
        "warm",
        "qualified",
        "hot",
        "call/proposal",
        "proposal",
        "payment_pending",
        "won",
        "lost",
    }


@dataclass
class LeadCandidate:
    tracker_row: int
    contact_name: str
    lead_source: str
    status: str
    budget_rub: int
    urgency_days: int
    offer: str
    score: int


def validate_tracker_row(row: dict[str, str], row_num: int) -> list[str]:
    """Validate tracker row and return list of warnings."""
    warnings: list[str] = []
    status = row.get("status", "").strip().lower()
    replied_val = row.get("replied", "").strip().lower()

    # Проверка replied согласованности
    if replied_val in ("true", "1", "yes"):
        expected_statuses = {
            "warm",
            "qualified",
            "hot",
            "call/proposal",
            "proposal",
            "payment_pending",
            "won",
            "lost",
        }
        if status not in expected_statuses:
            warnings.append(
                f"Row {row_num}: replied=true but status={status} (expected one of {expected_statuses})"
            )

    # Проверка replied_at при replied=true
    if replied_val in ("true", "1", "yes"):
        replied_at_val = row.get("replied_at", "").strip()
        if not replied_at_val:
            warnings.append(f"Row {row_num}: replied=true replied_at is empty")

    # Проверка бюджета
    budget = row.get("budget_rub", "").strip()
    if budget:
        try:
            val = int(float(budget))
            if val < 0:
                warnings.append(f"Row {row_num}:budget_rub={budget} (negative)")
        except Exception:
            warnings.append(f"Row {row_num}: budget_rub={budget} (invalid number)")

    return warnings


def to_int(value: str, default: int = 0) -> int:
    try:
        return int(float((value or "").strip()))
    except Exception:
        return default


def load_tracker_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Tracker not found: {path}")
    rows: list[dict[str, str]] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({k: row.get(k, "") for k in FIELDNAMES})
    return rows


def lead_score(row: dict[str, str]) -> int:
    status = row.get("status", "").strip().lower()
    urgency_days = to_int(row.get("urgency_days", ""), default=30)
    budget = to_int(row.get("budget_rub", ""), default=0)

    status_score = {
        "payment_pending": 95,
        "call/proposal": 90,
        "hot": 80,
        "qualified": 65,
        "warm": 45,
        "contacted": 30,
        "new": 20,
    }.get(status, 0)

    urgency_bonus = max(0, 20 - urgency_days)
    budget_bonus = min(20, budget // 500)
    return status_score + urgency_bonus + budget_bonus


def build_closing_queue(
    rows: list[dict[str, str]], limit: int, bottleneck: str | None = None
) -> list[LeadCandidate]:
    if bottleneck == "pipeline_gap_proposals":
        eligible_statuses = {"qualified", "warm"}
    else:
        eligible_statuses = {"payment_pending", "call/proposal", "hot", "qualified", "warm"}
    candidates: list[LeadCandidate] = []
    for idx, row in enumerate(rows, start=2):
        status = row.get("status", "").strip().lower()
        if status not in eligible_statuses:
            continue
        candidates.append(
            LeadCandidate(
                tracker_row=idx,
                contact_name=row.get("contact_name", "").strip() or "(no_name)",
                lead_source=row.get("lead_source", "").strip() or "-",
                status=status,
                budget_rub=to_int(row.get("budget_rub", ""), default=0),
                urgency_days=to_int(row.get("urgency_days", ""), default=30),
                offer=row.get("offer", "").strip() or "Standard API Audit",
                score=lead_score(row),
            )
        )
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:limit]


def create_message_for(candidate: LeadCandidate, bottleneck: str | None = None) -> str:
    if bottleneck == "pipeline_gap_proposals" and candidate.status in {"qualified", "warm"}:
        return (
            f"Привет, {candidate.contact_name}!Готов отправить КП по вашему проекту ({candidate.offer}). "
            f"Предлагаю созвон 10 минут для уточнения деталей, после чего сразу направлю КП с дедлайном на 24 часа. "
            f"Удобно закрыть вопросы сегодня?"
        )
    if candidate.status == "payment_pending":
        return (
            f"Привет, {candidate.contact_name}! Возвращаюсь по оплате: могу взять ваш кейс "
            f"в работу сегодня, слот держу до конца дня. Подтвердите, пожалуйста, готовность к оплате."
        )
    if candidate.status in {"call/proposal", "hot"}:
        return (
            f"{candidate.contact_name}, по вашему запросу подготовил(а) {candidate.offer}. "
            "Если ок, фиксирую условия и отправляю реквизиты сегодня. Удобно закрыть сегодня?"
        )
    if candidate.status == "qualified":
        return (
            f"{candidate.contact_name}, вижу высокий приоритет по вашей задаче. "
            "Предлагаю короткий созвон 10 минут и сразу после него отправляю КП с дедлайном на 24 часа."
        )
    return (
        f"{candidate.contact_name}, отправляю короткий follow-up: "
        "актуальна ли задача сейчас? Могу предложить экспресс-аудит и старт уже сегодня."
    )


def run_hybrid_day_json() -> dict[str, object]:
    if not HYBRID_RUN_SCRIPT.exists():
        raise FileNotFoundError(f"Not found: {HYBRID_RUN_SCRIPT}")

    cmd = [sys.executable, str(HYBRID_RUN_SCRIPT), "--json", "--cash-mode"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise RuntimeError(f"hybrid_day_run failed ({result.returncode}): {message[:500]}")

    text = result.stdout.strip()
    first = text.find("{")
    last = text.rfind("}")
    if first == -1 or last == -1 or last <= first:
        raise ValueError("Cannot parse JSON from hybrid_day_run output")
    return json.loads(text[first : last + 1])


def save_closing_queue(
    path: Path, queue: list[LeadCandidate], bottleneck: str | None = None
) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "rank",
                "tracker_row",
                "contact_name",
                "lead_source",
                "status",
                "budget_rub",
                "urgency_days",
                "offer",
                "score",
                "message",
            ],
        )
        writer.writeheader()
        for i, c in enumerate(queue, start=1):
            writer.writerow(
                {
                    "rank": i,
                    "tracker_row": c.tracker_row,
                    "contact_name": c.contact_name,
                    "lead_source": c.lead_source,
                    "status": c.status,
                    "budget_rub": c.budget_rub,
                    "urgency_days": c.urgency_days,
                    "offer": c.offer,
                    "score": c.score,
                    "message": create_message_for(c, bottleneck=bottleneck),
                }
            )


def save_playbook(
    path: Path,
    summary: dict[str, object],
    queue: list[LeadCandidate],
    bottleneck: str | None = None,
) -> None:
    cash_mode = summary.get("cash_mode", {})
    kpi = summary.get("kpi", {})
    bottleneck_val = cash_mode.get("bottleneck", "-") if isinstance(cash_mode, dict) else "-"
    reason = cash_mode.get("reason", "-") if isinstance(cash_mode, dict) else "-"
    contacts = kpi.get("contacts", 0) if isinstance(kpi, dict) else 0
    replies = kpi.get("replies", 0) if isinstance(kpi, dict) else 0
    qualified = kpi.get("qualified", 0) if isinstance(kpi, dict) else 0
    proposals = kpi.get("proposals", 0) if isinstance(kpi, dict) else 0
    won = kpi.get("won", 0) if isinstance(kpi, dict) else 0
    revenue = kpi.get("revenue_rub", 0) if isinstance(kpi, dict) else 0

    lines: list[str] = []
    lines.append("# Cash Autopilot Playbook")
    lines.append("")
    lines.append(f"- Date: `{date.today().isoformat()}`")
    lines.append(f"- Generated: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`")
    lines.append(f"- Bottleneck: `{bottleneck_val}` ({reason})")
    lines.append(
        f"- KPI: contacts={contacts}, replies={replies}, qualified={qualified}, "
        f"proposals={proposals}, won={won}, revenue={revenue} RUB"
    )
    lines.append("")

    if bottleneck_val == "pipeline_gap_proposals":
        lines.append("## SCENARIO: Qualified → Proposal Conversion")
        lines.append("")
        lines.append("**Problem:** Qualified leads exist, but no proposals sent.")
        lines.append(f"**Action:** Convert {qualified} qualified/warm leads to proposals today.")
        lines.append("")
        lines.append("### Top Leads to Convert (qualified/warm → proposal):")
        lines.append("")
        if not queue:
            lines.append("- No qualified/warm leads found. Add new leads to tracker.")
        for i, c in enumerate(queue, start=1):
            lines.append(
                f"{i}. **{c.contact_name}** | status={c.status} | source={c.lead_source} | "
                f"budget={c.budget_rub} RUB | urgency={c.urgency_days}d | score={c.score}"
            )
            lines.append(f"   - Message: {create_message_for(c, bottleneck=bottleneck_val)}")
            lines.append("")
        lines.append("### Daily Targets:")
        lines.append("")
        lines.append(f"- Send proposals to minimum 2 of {qualified} qualified leads.")
        lines.append("- Get response on each proposal within 48 hours.")
        lines.append("- Convert minimum 1 qualified lead to `call/proposal` status.")
        lines.append("")
        lines.append("### Closing Messages:")
        lines.append("")
        lines.append(
            "Each lead above has a personalized message. Use it for DM/call to convert qualified → proposal."
        )
    else:
        lines.append("## Top Closing Queue")
        lines.append("")
        if not queue:
            lines.append("- No hot/warm/qualified leads for closing. Add new contacts and retry.")
        for i, c in enumerate(queue, start=1):
            lines.append(
                f"- {i}. `{c.contact_name}` | status={c.status} | source={c.lead_source} | "
                f"budget={c.budget_rub} | urgency={c.urgency_days}d | score={c.score}"
            )
            lines.append(f"  - Message: {create_message_for(c, bottleneck=bottleneck_val)}")
        lines.append("")
        lines.append("## Money Targets Today")
        lines.append("")
        lines.append("- Перевести минимум 2 лида в `call/proposal`.")
        lines.append("- Перевести минимум 1 лид в `payment_pending`.")
        lines.append("- Закрыть минимум 1 оплату до конца дня.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cash autopilot: run + closing queue + DM scripts."
    )
    parser.add_argument("--tracker", default=str(TRACKER_DEFAULT))
    parser.add_argument("--out-dir", default=str(OUT_DIR_DEFAULT))
    parser.add_argument("--top", type=int, default=5, help="Top leads for closing queue")
    parser.add_argument(
        "--skip-run",
        action="store_true",
        help="Do not run hybrid_day_run.py; read latest saved summary if exists",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    summary_path = out_dir / f"CASH_AUTOPILOT_SUMMARY_{today}.json"
    queue_path = out_dir / f"CLOSING_QUEUE_{today}.csv"
    playbook_path = out_dir / f"CASH_AUTOPILOT_PLAYBOOK_{today}.md"

    if args.skip_run:
        if not summary_path.exists():
            print(f"Summary not found for --skip-run: {summary_path}")
            return 1
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    else:
        summary = run_hybrid_day_json()
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    bottleneck = None
    cash_mode = summary.get("cash_mode", {})
    if isinstance(cash_mode, dict):
        bottleneck = cash_mode.get("bottleneck")

    rows = load_tracker_rows(Path(args.tracker))
    queue = build_closing_queue(rows, limit=args.top, bottleneck=bottleneck)
    save_closing_queue(queue_path, queue, bottleneck=bottleneck)
    save_playbook(playbook_path, summary=summary, queue=queue, bottleneck=bottleneck)

    print("Cash autopilot complete")
    print(f"- Summary: {summary_path}")
    print(f"- Closing queue: {queue_path}")
    print(f"- Playbook: {playbook_path}")
    print(f"- Top leads selected: {len(queue)}")
    if bottleneck == "pipeline_gap_proposals":
        print(f"- Mode: QUALIFIED → PROPOSAL CONVERSION (bottleneck: {bottleneck})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
