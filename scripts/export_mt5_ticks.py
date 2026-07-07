#!/usr/bin/env python3
"""Export local Dukascopy ticks to MT5 custom-symbol tick CSV.

The parity gate needs BOTH engines fed identical data. This produces the CSV
that MT5's Symbols dialog imports as custom-symbol ticks (Symbols -> Create
Custom Symbol -> Ticks -> Import), so the Strategy Tester's "every tick based
on real ticks" mode replays exactly what the Python harness saw.

Format per MT5 tick import: one row per tick
    <DATE>\t<TIME>\t<BID>\t<ASK>\t<LAST>\t<VOLUME>\t<FLAGS>
with DATE=yyyy.MM.dd, TIME=HH:mm:ss.fff, LAST/VOLUME zero for FX,
FLAGS = 6 (TICK_FLAG_BID|TICK_FLAG_ASK = 2|4: both sides updated).

Usage:
    python3 scripts/export_mt5_ticks.py --pair EURUSD \
        --start 2026-05-01 --end 2026-05-30 --out reports/mt5_ticks_EURUSD.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from hft.data.storage import read_ticks

DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
FLAGS_BID_ASK = 6  # TICK_FLAG_BID (2) | TICK_FLAG_ASK (4)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", default="EURUSD")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    days = [d.strftime("%Y-%m-%d") for d in pd.date_range(args.start, args.end)]
    ticks = read_ticks(DATA_ROOT, args.pair, days)
    if ticks.empty:
        print("no local tick data; run scripts/download_data.py first")
        return 2

    t = ticks["time"].dt.tz_convert("UTC")
    out = pd.DataFrame(
        {
            "date": t.dt.strftime("%Y.%m.%d"),
            "time": t.dt.strftime("%H:%M:%S.%f").str[:-3],
            "bid": ticks["bid"].map(lambda x: f"{x:.5f}"),
            "ask": ticks["ask"].map(lambda x: f"{x:.5f}"),
            "last": "0.00000",
            "volume": 0,
            "flags": FLAGS_BID_ASK,
        }
    )
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, sep="\t", index=False, header=False)
    print(f"{len(out):,} ticks -> {path}")
    print("Import in MT5: View > Symbols > Create Custom Symbol > Ticks > Import; "
          "note MT5 imports tick times in the terminal's timezone — set the custom "
          "symbol's timezone to UTC (or shift here) before the parity run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
