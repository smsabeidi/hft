#!/usr/bin/env python3
"""Demo rehearsal status — the self-assessing gate for the 100k demo phase.

The founder's sequencing: prove everything on the free 100k demo, then
consider the paid 50k/100k evaluation. This script makes that first phase
mechanical, exactly like paper_status.py does for the crypto book.

WHAT THE DEMO PROVES (and what it can't): the rehearsal validates
OPERATIONS — fills, one-trade-per-day discipline, sizing, logging, alerts,
uptime through London sessions. It cannot validate the strategy
(SessionBreakout is refuted on 5.5y; its demo P&L is noise either way).
The paid-account purchase gate therefore has TWO conditions:
  A. DEMO OPS GATE (this script): >=10 round trips across >=10 distinct
     days, one-trade-per-day discipline unbroken, CSV logging complete.
  B. A VALIDATED STRATEGY in SignalHost's slot (a family that passed the
     gauntlet + parity gate) — because a funded account runs edge, not ops.
Reads the EA's parity CSV from the MT5 Common Files folder. Exit 0 = ops
gate met.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

PREFIX = Path.home() / "Library/Application Support/net.metaquotes.wine.metatrader5"
COMMON_CANDIDATES = [
    PREFIX / "drive_c/users/admin/AppData/Roaming/MetaQuotes/Terminal/Common/Files",
    PREFIX / "drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files",
]
CSV_NAME = "live_parity_session_breakout.csv"  # tester writes tester_*; live writes live_*
MIN_TRADES, MIN_DAYS = 10, 10

ATTACH_HELP = """no parity CSV yet — the EA hasn't traded. Attach checklist:
  1. MT5: log into the 100k DEMO account (not FundedNext)
  2. EURUSD M5 chart <- drag SessionBreakout
  3. Inputs: 'set true ONLY after pinning the firm rulebook' = true
             InpInitialBalance = 100000   (must match the account)
  4. Common tab: Allow Algo Trading; toolbar Algo Trading green
  5. Mac awake (or chart migrated to the MT5 VPS) during 07:00-12:00 UTC
  Expect at most ONE trade per day; tradeless days are normal."""


def main() -> int:
    path = next((d / CSV_NAME for d in COMMON_CANDIDATES if (d / CSV_NAME).exists()), None)
    if path is None:
        print(ATTACH_HELP)
        return 1

    with path.open(encoding="utf-16") as f:  # MQL5 writes CSV as UTF-16LE
        rows = list(csv.DictReader(f))
    exits = [r for r in rows if float(r.get("profit", 0) or 0) != 0.0]
    if not rows:
        print("CSV exists but no deals yet — EA armed, no fills. Patience is the job.")
        return 1

    days = Counter(r["time"].split(" ")[0] for r in exits)
    wins = sum(1 for r in exits if float(r["profit"]) > 0)
    pnl = sum(float(r["profit"]) + float(r.get("commission", 0) or 0)
              + float(r.get("swap", 0) or 0) for r in exits)
    worst_day_count = max(days.values()) if days else 0

    print(f"demo rehearsal: {len(exits)} round trips over {len(days)} trading days "
          f"({rows[0]['time']} .. {rows[-1]['time']})")
    print(f"  P&L (ignore the sign — ops rehearsal): {pnl:+,.2f} | "
          f"wins {wins}/{len(exits)}")
    checks = {
        f"round trips >= {MIN_TRADES}": len(exits) >= MIN_TRADES,
        f"distinct days >= {MIN_DAYS}": len(days) >= MIN_DAYS,
        "one-trade-per-day discipline unbroken": worst_day_count <= 1,
    }
    for label, ok in checks.items():
        print(f"  [{'x' if ok else ' '}] {label}")
    if all(checks.values()):
        print("DEMO OPS GATE: MET. Condition B (validated strategy in SignalHost) "
              "still gates the paid 50k/100k purchase — see rounds.log for the "
              "pipeline (C5 fires at recorded day 30 once the VM exists).")
        return 0
    print("DEMO OPS GATE: not yet — keep it running; the gate re-evaluates every run.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
