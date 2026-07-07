#!/usr/bin/env python3
"""Download Dukascopy tick data into the local parquet store.

Usage:
    python3 scripts/download_data.py --pair EURUSD --start 2021-01-04 --end 2026-06-30
    python3 scripts/download_data.py --pair EURUSD --days 30   # last 30 calendar days

Every downloaded day passes through the sanity validator; days with dropped
ticks or gaps are reported. Data lands in data/ticks/{PAIR}/{DAY}.parquet.
Weekends are skipped. Re-runs skip days that already exist (idempotent).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hft.data.dukascopy import download_day
from hft.data.sanity import validate_ticks
from hft.data.storage import tick_path, write_ticks

DATA_ROOT = Path(__file__).resolve().parents[1] / "data"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", default="EURUSD")
    ap.add_argument("--start", help="YYYY-MM-DD (UTC)")
    ap.add_argument("--end", help="YYYY-MM-DD (UTC), inclusive")
    ap.add_argument("--days", type=int, help="alternative: last N calendar days")
    args = ap.parse_args()

    if args.days:
        end = datetime.now(timezone.utc) - timedelta(days=1)
        start = end - timedelta(days=args.days)
    elif args.start and args.end:
        start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)
    else:
        ap.error("provide --start/--end or --days")
        return 2

    day = start
    n_ok, n_skip, n_empty = 0, 0, 0
    while day <= end:
        if day.weekday() >= 5:  # Sat/Sun have no meaningful FX data
            day += timedelta(days=1)
            continue
        day_str = day.strftime("%Y-%m-%d")
        if tick_path(DATA_ROOT, args.pair, day_str).exists():
            n_skip += 1
            day += timedelta(days=1)
            continue
        ticks = download_day(args.pair, day)
        if ticks.empty:
            print(f"{day_str}: no data (holiday?)")
            n_empty += 1
        else:
            clean, report = validate_ticks(ticks)
            write_ticks(clean, DATA_ROOT, args.pair, day_str)
            flag = ""
            if report.dropped or report.gaps:
                flag = f"  [dropped {report.dropped}, gaps {len(report.gaps)}]"
            print(f"{day_str}: {len(clean):,} ticks{flag}")
            n_ok += 1
        day += timedelta(days=1)

    print(f"\ndone: {n_ok} days downloaded, {n_skip} already present, {n_empty} empty")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
