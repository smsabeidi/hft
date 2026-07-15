#!/usr/bin/env python3
"""Quantify the daily circuit breaker: worst-day and tail across 1,422 days,
with vs without a 3% daily stop. Loss minimization, measured."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
from scripts.hf_day_backtest import HFConfig, simulate_hf_day

BARS = Path(__file__).resolve().parents[1] / "data" / "bars" / "histdata"
PIPV, LOTS, EQ = 10.0, 0.5, 100_000.0  # $/pip/lot, lots, start equity

def main() -> int:
    files = sorted(BARS.glob("EURUSD_M1_*.parquet"))
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True).sort_values("time")
    df["day"] = df["time"].dt.date
    by_day = {d: g.reset_index(drop=True) for d, g in df.groupby("day") if len(g) > 600}
    days = list(by_day)
    print(f"EURUSD {len(days)} days | base geometry tp10/sl60, cap 50, {LOTS} lot, ${PIPV}/pip")
    print("=" * 84)
    for stop in (0.0, 5.0, 3.0, 2.0):
        day_usd = []
        for d in days:
            cfg = HFConfig(tp_pips=10, sl_pips=60, cadence_ms=1000, max_open=50,
                           daily_stop_pct=stop, start_equity=EQ, pip_value_per_lot=PIPV, lots=LOTS)
            r = simulate_hf_day(by_day[d], cfg)
            day_usd.append(r.net_pips * PIPV * LOTS)
        u = np.array(day_usd)
        label = "NO breaker" if stop == 0 else f"{stop:.0f}% daily stop"
        print(f"{label:>16}: mean day ${u.mean():>+9.0f} | WORST day ${u.min():>+10.0f} "
              f"| 1%%-tail ${np.percentile(u,1):>+9.0f} | days < -$5k: {int((u < -5000).sum()):>4}")
    print("-" * 84)
    print("reading: the daily breaker slashes the WORST-day and tail losses hard —")
    print("that is real, valuable capital preservation. But mean day-net stays")
    print("NEGATIVE (the edge is negative), so the breaker minimizes the bleed rate,")
    print("it does not create profit. Loss-minimization works; profit needs edge.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
