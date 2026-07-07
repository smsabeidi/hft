#!/usr/bin/env python3
"""Recorder coverage report — permitted QA (no signal content).

Prints per-day minute coverage per instrument and the C5 data-floor status.
This is the report the pre-registration requires publishing with any C5
round; scripts/run_c5_round.py refuses to run while the floor is unmet.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hft.crypto.coverage import C5_INSTRUMENTS, c5_floor, minute_coverage

DATA_ROOT = Path(__file__).resolve().parents[1] / "data" / "crypto"


def main() -> int:
    for inst in C5_INSTRUMENTS:
        cov = minute_coverage(DATA_ROOT, inst)
        if cov.empty:
            print(f"{inst}: no recorded data")
            continue
        print(f"{inst}:")
        for _, r in cov.iterrows():
            print(f"  {r['date']}  {int(r['minutes']):>5} min  {r['coverage']:>6.1%}")
    status = c5_floor(DATA_ROOT)
    print("-" * 60)
    print(f"C5 data floor: {'MET' if status.met else 'NOT MET'} — {status.detail}")
    return 0 if status.met else 1


if __name__ == "__main__":
    raise SystemExit(main())
