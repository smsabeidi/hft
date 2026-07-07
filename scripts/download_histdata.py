#!/usr/bin/env python3
"""Download HistData free M1 history into data/bars/histdata/.

Usage:
    python3 scripts/download_histdata.py --pair EURUSD --from-year 2021 --to-year 2026

Full years come as one zip each; the current year is fetched month by month.
Idempotent: existing parquet files are skipped. See hft/data/histdata.py for
the EST->UTC and no-spread caveats.
"""

from __future__ import annotations

import argparse
import sys
import time as time_mod
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hft.data.histdata import download_m1, parse_zip

OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "bars" / "histdata"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", default="EURUSD")
    ap.add_argument("--from-year", type=int, default=2021)
    ap.add_argument("--to-year", type=int, default=datetime.now(timezone.utc).year)
    ap.add_argument("--delay-s", type=float, default=2.0)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)

    for year in range(args.from_year, args.to_year + 1):
        if year < now.year:
            targets = [(year, None)]
        else:
            targets = [(year, m) for m in range(1, now.month)]  # complete months only
        for y, m in targets:
            tag = f"{y}" if m is None else f"{y}-{m:02d}"
            path = OUT_DIR / f"{args.pair.upper()}_M1_{tag}.parquet"
            if path.exists():
                print(f"{tag}: already present")
                continue
            try:
                bars = parse_zip(download_m1(args.pair, y, m))
            except Exception as e:
                print(f"{tag}: FAILED — {type(e).__name__}: {str(e)[:100]}")
                continue
            bars.to_parquet(path, index=False)
            print(f"{tag}: {len(bars):,} bars -> {path.name}")
            time_mod.sleep(args.delay_s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
