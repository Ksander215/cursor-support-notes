#!/usr/bin/env python3
"""Generate compact KPI summary from outbound tracker CSV."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

REPLIED_STATUSES = {
    "warm",
    "qualified",
    "hot",
    "call/proposal",
    "proposal",
    "payment_pending",
    "won",
    "lost",
}
QUALIFIED_STATUSES = {"qualified", "hot", "warm"}
PROPOSAL_STATUSES = {"call/proposal", "proposal", "payment_pending"}


def get_replied(row: dict[str, str]) -> bool:
    """Check if lead replied (backward-compatible).

    Priority:
    1. Explicit 'replied' column (true/false)
    2. Fallback to status-based logic (REPLIED_STATUSES)
    """
    replied_val = row.get("replied", "").strip().lower()
    if replied_val in ("true", "1", "yes"):
        return True
    if replied_val in ("false", "0", "no"):
        return False
    # fallback на статусную логику при пустом/отсутствующем replied
    return row.get("status", "").lower() in REPLIED_STATUSES


def safe_div(num: int, den: int) -> float:
    if den <= 0:
        return 0.0
    return num / den


def to_int(value: str) -> int:
    try:
        return int(float(value.strip()))
    except Exception:
        return 0


def build_kpi(rows: list[dict[str, str]]) -> dict[str, object]:
    contacts = len(rows)
    replies = sum(1 for r in rows if get_replied(r))
    qualified = sum(1 for r in rows if r.get("status", "").lower() in QUALIFIED_STATUSES)
    proposals = sum(1 for r in rows if r.get("status", "").lower() in PROPOSAL_STATUSES)
    won_rows = [r for r in rows if r.get("status", "").lower() == "won"]
    won = len(won_rows)
    revenue = sum(to_int(r.get("deal_value_rub", "0")) for r in won_rows)
    top_channels = Counter(r.get("lead_source", "").strip() for r in rows if r.get("lead_source"))
    top_channel = top_channels.most_common(1)[0][0] if top_channels else "-"
    avg_check = (revenue / won) if won else 0.0

    rates = {
        "reply_rate": safe_div(replies, contacts),
        "qual_rate": safe_div(qualified, replies),
        "proposal_rate": safe_div(proposals, qualified),
        "payment_rate": safe_div(won, proposals),
        "qualified_to_won": safe_div(won, qualified),
    }

    return {
        "contacts": contacts,
        "replies": replies,
        "qualified": qualified,
        "proposals": proposals,
        "won": won,
        "revenue_rub": revenue,
        "average_check_rub": round(avg_check, 2),
        "top_channel": top_channel,
        "rates": {k: round(v, 4) for k, v in rates.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Revenue KPI summary from tracker CSV.")
    parser.add_argument(
        "--tracker",
        default="agent_outputs/OUTBOUND_72H_TRACKER.csv",
        help="Path to outbound tracker CSV",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output KPI as JSON",
    )
    args = parser.parse_args()

    tracker_path = Path(args.tracker)
    if not tracker_path.exists():
        print(f"Tracker not found: {tracker_path}")
        return 1

    rows: list[dict[str, str]] = []
    with tracker_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows.extend(reader)

    kpi = build_kpi(rows)

    if args.json:
        print(json.dumps(kpi, ensure_ascii=False, indent=2))
        return 0

    rates = kpi["rates"]
    print("Revenue KPI summary")
    print("-------------------")
    print(f"Contacts: {kpi['contacts']}")
    print(f"Replies: {kpi['replies']} ({rates['reply_rate'] * 100:.2f}%)")
    print(f"Qualified: {kpi['qualified']} ({rates['qual_rate'] * 100:.2f}% от replies)")
    print(
        f"Proposals/payment pending: {kpi['proposals']} ({rates['proposal_rate'] * 100:.2f}% от qualified)"
    )
    print(f"Won: {kpi['won']} ({rates['payment_rate'] * 100:.2f}% от proposals)")
    print(f"Revenue (RUB): {kpi['revenue_rub']}")
    print(f"Average check (RUB): {kpi['average_check_rub']:.2f}")
    print(f"Top channel: {kpi['top_channel']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
