#!/usr/bin/env python3
"""
Hybrid daily run orchestrator.

Runs 4 steps of hybrid daily workflow in sequence:
1. outbound_checklist_automation --queue-selected
2. hybrid_tracking_sync
3. followup_scheduler
4. revenue_kpi_report

Features:
- Sequential execution with error handling
- --continue-on-error flag to continue after failures
- --json flag for JSON output
- Compact daily dashboard on completion
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent

STEPS = [
    {
        "name": "outbound_checklist_automation",
        "script": "outbound_checklist_automation.py",
        "args": ["--queue-selected"],
        "description": "Queue selected outbound tasks",
    },
    {
        "name": "hybrid_tracking_sync",
        "script": "hybrid_tracking_sync.py",
        "args": [],
        "description": "Sync hybrid tracking data",
    },
    {
        "name": "followup_scheduler",
        "script": "followup_scheduler.py",
        "args": [],
        "description": "Schedule follow-ups",
    },
    {
        "name": "revenue_kpi_report",
        "script": "revenue_kpi_report.py",
        "args": [],
        "description": "Generate revenue KPI report",
    },
]


@dataclass
class StepResult:
    name: str
    description: str
    status: str
    exit_code: int
    duration_sec: float
    error_message: str | None = None
    stdout: str = ""
    stderr: str = ""


@dataclass
class CashModeAnalysis:
    bottleneck: str
    reason: str
    actions: list[str]
    targets: list[str]


THRESHOLDS = {
    "contacts_per_day": 20,
    "reply_rate": 0.20,
    "qual_rate": 0.40,
    "payment_rate": 0.30,
}

Bottleneck = str
PRIORITY: list[Bottleneck] = [
    "proposal_to_pay_low",
    "reply_rate_low",
    "traffic_low",
    "lead_quality_low",
]


def run_step(step: dict[str, str | list[str]], extra_args: list[str] | None = None) -> StepResult:
    name = step["name"]
    script = step["script"]
    args = step.get("args", [])
    description = step["description"]
    if extra_args:
        args = list(args) + extra_args

    script_path = SCRIPTS_DIR / script
    if not script_path.exists():
        return StepResult(
            name=name,
            description=description,
            status="error",
            exit_code=1,
            duration_sec=0.0,
            error_message=f"Script not found: {script_path}",
            stdout="",
            stderr="",
        )

    cmd = [sys.executable, str(script_path), *list(args)]

    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        duration = time.time() - start_time

        if result.returncode == 0:
            return StepResult(
                name=name,
                description=description,
                status="success",
                exit_code=0,
                duration_sec=round(duration, 2),
                stdout=result.stdout,
                stderr=result.stderr,
            )
        else:
            error_msg = result.stderr.strip() if result.stderr else result.stdout.strip()
            return StepResult(
                name=name,
                description=description,
                status="failed",
                exit_code=result.returncode,
                duration_sec=round(duration, 2),
                error_message=error_msg[:500] if error_msg else "Unknown error",
                stdout=result.stdout,
                stderr=result.stderr,
            )
    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        return StepResult(
            name=name,
            description=description,
            status="timeout",
            exit_code=124,
            duration_sec=round(duration, 2),
            error_message="Step exceeded 300s timeout",
            stdout="",
            stderr="",
        )
    except Exception as e:
        duration = time.time() - start_time
        return StepResult(
            name=name,
            description=description,
            status="error",
            exit_code=1,
            duration_sec=round(duration, 2),
            error_message=str(e),
            stdout="",
            stderr="",
        )


def print_step_result(result: StepResult, verbose: bool = False) -> None:
    status_icon = "✓" if result.status == "success" else "✗"
    print(f"  [{status_icon}] {result.name}: {result.status} ({result.duration_sec}s)")

    if verbose and result.error_message:
        print(f"      Error: {result.error_message[:200]}")


def print_dashboard(results: list[StepResult]) -> None:
    total = len(results)
    success = sum(1 for r in results if r.status == "success")
    failed = sum(1 for r in results if r.status != "success")
    total_duration = sum(r.duration_sec for r in results)

    print("\n" + "=" * 50)
    print("DAILY DASHBOARD")
    print("=" * 50)
    print(f"Steps: {total}")
    print(f"Success: {success}")
    print(f"Failed: {failed}")
    print(f"Total duration: {total_duration:.2f}s")

    if failed > 0:
        print("\nFAILED STEPS:")
        for r in results:
            if r.status != "success":
                print(f"  - {r.name}: {r.error_message or 'Unknown error'}")

    print("=" * 50)


def print_json_summary(results: list[StepResult]) -> None:
    summary = build_json_summary(results)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def build_json_summary(
    results: list[StepResult],
    cash_analysis: CashModeAnalysis | None = None,
    kpi_snapshot: dict[str, object] | None = None,
) -> dict[str, object]:
    total_duration = sum(r.duration_sec for r in results)
    success_count = sum(1 for r in results if r.status == "success")

    summary: dict[str, object] = {
        "timestamp": datetime.now().isoformat(),
        "total_steps": len(results),
        "success": success_count,
        "failed": len(results) - success_count,
        "total_duration_sec": round(total_duration, 2),
        "steps": [
            {
                "step": r.name,
                "status": r.status,
                "duration_sec": r.duration_sec,
                "exit_code": r.exit_code,
                "error": r.error_message,
            }
            for r in results
        ],
    }
    if cash_analysis:
        summary["cash_mode"] = {
            "bottleneck": cash_analysis.bottleneck,
            "reason": cash_analysis.reason,
            "actions": cash_analysis.actions,
            "targets": cash_analysis.targets,
        }
    if kpi_snapshot:
        summary["kpi"] = kpi_snapshot
    return summary


def extract_json_block(raw_text: str) -> dict[str, object] | None:
    text = raw_text.strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    first = text.find("{")
    last = text.rfind("}")
    if first == -1 or last == -1 or last <= first:
        return None
    candidate = text[first : last + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def analyze_bottleneck(kpi: dict[str, object]) -> CashModeAnalysis:
    contacts = int(kpi.get("contacts", 0) or 0)
    replies = int(kpi.get("replies", 0) or 0)
    qualified = int(kpi.get("qualified", 0) or 0)
    proposals = int(kpi.get("proposals", 0) or 0)
    won = int(kpi.get("won", 0) or 0)
    rates = kpi.get("rates", {})
    if not isinstance(rates, dict):
        rates = {}
    reply_rate = float(rates.get("reply_rate", 0.0) or 0.0)
    qual_rate = float(rates.get("qual_rate", 0.0) or 0.0)
    payment_rate = float(rates.get("payment_rate", 0.0) or 0.0)

    if proposals == 0 and qualified > 0:
        return CashModeAnalysis(
            bottleneck="pipeline_gap_proposals",
            reason=f"{qualified} qualified лид(а), но 0 proposals — разрыв между qual и КП",
            actions=[
                "Срочно отправить КП всем warm/qualified лидам сегодня.",
                "Проверить есть ли контакт для follow-up по каждому qualified.",
                "Подготовить шаблон КП для быстрой отправки.",
            ],
            targets=[
                f"Вывести минимум 2 из {qualified} qualified в proposal сегодня.",
                "Получить ответ по каждому отправленному КП в течение 48 часов.",
            ],
        )

    red_flags: dict[Bottleneck, bool] = {
        "traffic_low": contacts < THRESHOLDS["contacts_per_day"],
        "reply_rate_low": contacts > 0 and reply_rate < THRESHOLDS["reply_rate"],
        "lead_quality_low": replies > 0 and qual_rate < THRESHOLDS["qual_rate"],
        "proposal_to_pay_low": proposals > 0 and payment_rate < THRESHOLDS["payment_rate"],
    }

    bottleneck = next((name for name in PRIORITY if red_flags.get(name)), "no_critical_bottleneck")

    if bottleneck == "proposal_to_pay_low":
        need_won = max(0, math.ceil(proposals * THRESHOLDS["payment_rate"]) - won)
        return CashModeAnalysis(
            bottleneck=bottleneck,
            reason=f"{payment_rate * 100:.1f}% < {THRESHOLDS['payment_rate'] * 100:.0f}% по won/proposals",
            actions=[
                "Сделать дожим по всем open КП: звонок + персональный DM сегодня.",
                "Добавить дедлайн в КП на 24 часа и конкретный CTA по оплате.",
                "Для сильных warm лидов предложить bundle как ускоренный выбор.",
            ],
            targets=[
                f"Закрыть минимум +{need_won} оплат(ы), чтобы выйти на {THRESHOLDS['payment_rate'] * 100:.0f}% close rate.",
                "Провести минимум 2 follow-up звонка по отправленным КП.",
                "Получить подтверждение оплаты по pending-сделкам сегодня.",
            ],
        )

    if bottleneck == "reply_rate_low":
        need_replies = max(0, math.ceil(contacts * THRESHOLDS["reply_rate"]) - replies)
        return CashModeAnalysis(
            bottleneck=bottleneck,
            reason=f"{reply_rate * 100:.1f}% < {THRESHOLDS['reply_rate'] * 100:.0f}% по replies/contacts",
            actions=[
                "Сделать A/B двух первых сообщений (оффер vs боль) на новой выборке.",
                "Добавить 1 персонализированный факт о клиенте в каждый outreach.",
                "Перенести отправки в самые ответные слоты (день/вечер) и сразу ставить follow-up.",
            ],
            targets=[
                f"Добрать минимум +{need_replies} ответ(а), чтобы выйти на {THRESHOLDS['reply_rate'] * 100:.0f}% reply rate.",
                "Сделать не меньше 20 исходящих касаний сегодня.",
                "Поставить follow-up для всех unanswered контактов в течение 24 часов.",
            ],
        )

    if bottleneck == "lead_quality_low":
        need_qualified = max(0, math.ceil(replies * THRESHOLDS["qual_rate"]) - qualified)
        return CashModeAnalysis(
            bottleneck=bottleneck,
            reason=f"{qual_rate * 100:.1f}% < {THRESHOLDS['qual_rate'] * 100:.0f}% по qualified/replies",
            actions=[
                "Ужесточить ICP-фильтр перед outreach (бюджет, срочность, тип проекта).",
                "Добавить 2 квалифицирующих вопроса в первый диалог.",
                "Остановить работу с не-ICP лидами и перераспределить время на hot/warm.",
            ],
            targets=[
                f"Добрать минимум +{need_qualified} qualified лид(ов), чтобы выйти на {THRESHOLDS['qual_rate'] * 100:.0f}% qual rate.",
                "Не отправлять КП до прохождения базовой квалификации.",
                "Сфокусировать 70% времени на ICP-сегменте.",
            ],
        )

    if bottleneck == "no_critical_bottleneck":
        return CashModeAnalysis(
            bottleneck=bottleneck,
            reason="Критичных просадок по порогам не найдено",
            actions=[
                "Сфокусироваться на оплатах из hot/warm: дожать pending сделки сегодня.",
                "Увеличить долю лидов, доходящих до этапа proposal/payment_pending.",
                "Сделать 1 микро-тест оффера для роста среднего чека (bundle/fast-track).",
            ],
            targets=[
                "Удержать минимум 20 контактов в день и 20%+ reply rate.",
                "Вывести в proposal минимум 2 квалифицированных лида за день.",
                "Закрыть минимум 1 оплату в день в среднем по неделе.",
            ],
        )

    need_contacts = max(1, THRESHOLDS["contacts_per_day"] - contacts)
    return CashModeAnalysis(
        bottleneck="traffic_low",
        reason=f"{contacts} < {THRESHOLDS['contacts_per_day']} по contacts/day",
        actions=[
            "Добавить минимум +10 исходящих DM по ICP из Telegram/бирж.",
            "Опубликовать 2 коротких оффера в релевантных чатах и на биржах.",
            "Подключить реферальный поток: запросить 3 интро у текущих контактов.",
        ],
        targets=[
            f"Добрать минимум +{need_contacts} контактов, чтобы выйти на {THRESHOLDS['contacts_per_day']} контактов/день.",
            "Сформировать список из 20 приоритетных контактов на завтра.",
            "Проверить reply-rate в конце дня после нового объёма.",
        ],
    )


def print_cash_mode(kpi: dict[str, object], analysis: CashModeAnalysis) -> None:
    contacts = int(kpi.get("contacts", 0) or 0)
    replies = int(kpi.get("replies", 0) or 0)
    qualified = int(kpi.get("qualified", 0) or 0)
    proposals = int(kpi.get("proposals", 0) or 0)
    won = int(kpi.get("won", 0) or 0)
    revenue = int(kpi.get("revenue_rub", 0) or 0)
    rates = kpi.get("rates", {})
    if not isinstance(rates, dict):
        rates = {}
    reply_rate = float(rates.get("reply_rate", 0.0) or 0.0) * 100
    qual_rate = float(rates.get("qual_rate", 0.0) or 0.0) * 100
    payment_rate = float(rates.get("payment_rate", 0.0) or 0.0) * 100

    print("\n" + "=" * 50)
    print("CASH-MODE ANALYSIS")
    print("=" * 50)
    print("KPI Snapshot:")
    print(f"  Contacts: {contacts}")
    print(f"  Replies: {replies} ({reply_rate:.1f}% reply rate)")
    print(f"  Qualified: {qualified} ({qual_rate:.1f}% qual rate)")
    print(f"  Proposals: {proposals}")
    print(f"  Won: {won} ({payment_rate:.1f}% close rate)")
    print(f"  Revenue: {revenue} RUB")
    print("")
    print(f"BOTTLENECK: {analysis.bottleneck} ({analysis.reason})")
    print("")
    print("TOP-3 ACTIONS FOR TODAY:")
    for i, action in enumerate(analysis.actions, start=1):
        print(f"  {i}. {action}")
    print("")
    print("DAILY TARGET:")
    for target in analysis.targets:
        print(f"  - {target}")
    print("=" * 50)


def build_text_report(
    results: list[StepResult],
    cash_analysis: CashModeAnalysis | None = None,
    kpi_snapshot: dict[str, object] | None = None,
) -> str:
    lines: list[str] = []
    total = len(results)
    success = sum(1 for r in results if r.status == "success")
    failed = sum(1 for r in results if r.status != "success")
    total_duration = sum(r.duration_sec for r in results)
    lines.append("HYBRID DAY RUN REPORT")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("Steps:")
    for r in results:
        lines.append(f"- {r.name}: {r.status} (exit={r.exit_code}, {r.duration_sec:.2f}s)")
    lines.append("")
    lines.append(f"Total steps: {total}")
    lines.append(f"Success: {success}")
    lines.append(f"Failed: {failed}")
    lines.append(f"Total duration: {total_duration:.2f}s")
    if cash_analysis and kpi_snapshot:
        rates = kpi_snapshot.get("rates", {})
        reply_rate = (
            float(rates.get("reply_rate", 0.0) or 0.0) * 100 if isinstance(rates, dict) else 0.0
        )
        qual_rate = (
            float(rates.get("qual_rate", 0.0) or 0.0) * 100 if isinstance(rates, dict) else 0.0
        )
        payment_rate = (
            float(rates.get("payment_rate", 0.0) or 0.0) * 100 if isinstance(rates, dict) else 0.0
        )
        lines.append("")
        lines.append("Cash-mode:")
        lines.append(
            f"- KPI: contacts={kpi_snapshot.get('contacts', 0)}, replies={kpi_snapshot.get('replies', 0)} ({reply_rate:.1f}%), "
            f"qualified={kpi_snapshot.get('qualified', 0)} ({qual_rate:.1f}%), proposals={kpi_snapshot.get('proposals', 0)}, "
            f"won={kpi_snapshot.get('won', 0)} ({payment_rate:.1f}%), revenue={kpi_snapshot.get('revenue_rub', 0)} RUB"
        )
        lines.append(f"- Bottleneck: {cash_analysis.bottleneck} ({cash_analysis.reason})")
        lines.append("- Actions:")
        for action in cash_analysis.actions:
            lines.append(f"  * {action}")
        lines.append("- Targets:")
        for target in cash_analysis.targets:
            lines.append(f"  * {target}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Hybrid daily run orchestrator. Runs 4 steps in sequence.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/hybrid_day_run.py
  python scripts/hybrid_day_run.py --continue-on-error
  python scripts/hybrid_day_run.py --json
        """,
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue execution even if a step fails",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON summary instead of text",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show more details for each step",
    )
    parser.add_argument(
        "--cash-mode",
        action="store_true",
        help="Analyze KPI and print cash-focused actions after run",
    )
    parser.add_argument(
        "--save-report",
        help="Save final report to file (text by default, JSON with --json)",
    )
    args = parser.parse_args()

    if not args.json:
        print("=" * 50)
        print("HYBRID DAY RUN")
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 50)

    results: list[StepResult] = []
    has_failure = False
    cash_analysis: CashModeAnalysis | None = None
    kpi_snapshot: dict[str, object] | None = None

    for i, step in enumerate(STEPS, 1):
        if not args.json:
            print(f"\n[{i}/{len(STEPS)}] {step['description']}...")

        extra_args: list[str] = []
        if args.cash_mode and step["name"] == "revenue_kpi_report":
            extra_args = ["--json"]
        result = run_step(step, extra_args=extra_args)
        results.append(result)

        if not args.json:
            print_step_result(result, args.verbose)

        if result.status != "success":
            has_failure = True
            if not args.continue_on_error:
                if not args.json:
                    print(f"\n✗ Pipeline stopped at step: {step['name']}")
                    print(f"  Exit code: {result.exit_code}")
                    if result.error_message:
                        print(f"  Error: {result.error_message}")
                else:
                    print_json_summary(results)
                return result.exit_code

    if args.cash_mode:
        kpi_step = next((r for r in results if r.name == "revenue_kpi_report"), None)
        if kpi_step:
            parsed_kpi = extract_json_block(kpi_step.stdout)
            if parsed_kpi:
                kpi_snapshot = parsed_kpi
                cash_analysis = analyze_bottleneck(parsed_kpi)
                if not args.json:
                    print_cash_mode(parsed_kpi, cash_analysis)
            elif not args.json:
                print("\n[!] cash-mode: не удалось распарсить KPI JSON из revenue_kpi_report.")

    if args.json:
        summary = build_json_summary(
            results, cash_analysis=cash_analysis, kpi_snapshot=kpi_snapshot
        )
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print_dashboard(results)

    if args.save_report:
        report_path = Path(args.save_report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        if args.json:
            summary = build_json_summary(
                results, cash_analysis=cash_analysis, kpi_snapshot=kpi_snapshot
            )
            report_path.write_text(
                json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        else:
            report_path.write_text(
                build_text_report(results, cash_analysis=cash_analysis, kpi_snapshot=kpi_snapshot),
                encoding="utf-8",
            )
        if not args.json:
            print(f"\nReport saved to: {report_path}")

    if has_failure:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
