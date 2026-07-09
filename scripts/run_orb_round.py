#!/usr/bin/env python3
"""us_open_orb_indices round 1 (of 2) — founder-directed ORB research.

Spec and gate FROZEN in reports/orb_research.md before this run: US500 +
NAS100 M1 (histdata, UTC), NY-clock opening range at the 09:30 cash open,
grid (range 15/30 min x target none/4R), stop at the opposite range edge,
15:55 NY hard exit, 2.5bp RT costs, 500/120 walk-forward.

GATE: pooled OOS >= 100 trades, mean net > 0 bps, t >= 2.0,
window stability >= 0.6.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from scipy import stats

from hft.strategies.orb import walk_forward_orb

ROOT = Path(__file__).resolve().parents[1]
BARS_DIR = ROOT / "data" / "bars" / "histdata"
ROUNDS_LOG = ROOT / "reports" / "rounds.log"
SYMBOLS = {"US500": "SPXUSD", "NAS100": "NSXUSD"}


def main() -> int:
    all_trades, all_windows = [], []
    for label, stem in SYMBOLS.items():
        files = sorted(BARS_DIR.glob(f"{stem}_M1_*.parquet"))
        m1 = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
        windows, trades = walk_forward_orb(m1, label)
        nets = np.array([t.net_bps for t in trades])
        wr = float((nets > 0).mean()) if len(nets) else 0.0
        print(f"{label}: {len(windows)} windows, {len(trades)} OOS trades, "
              f"win rate {wr:.0%}, mean net {nets.mean() if len(nets) else 0:+.2f} bps")
        for w in windows:
            print(f"    {w.test_start} {w.params} test_net={w.test_net:+.0f}bps "
                  f"({w.test_trades} trades)")
        all_trades.extend(trades)
        all_windows.extend(windows)

    nets = np.array([t.net_bps for t in all_trades])
    n = len(nets)
    if n < 2:
        print("insufficient OOS trades -> FAIL")
        return 1
    mean = float(nets.mean())
    t = float(mean / (nets.std(ddof=1) / np.sqrt(n))) if nets.std(ddof=1) > 0 else 0.0
    lo, hi = stats.t.interval(0.95, df=n - 1, loc=mean, scale=nets.std(ddof=1) / np.sqrt(n))
    stab = sum(1 for w in all_windows if w.test_trades > 0 and w.test_net > 0) / len(all_windows)
    wr = float((nets > 0).mean())
    passed = n >= 100 and mean > 0 and t >= 2.0 and stab >= 0.6

    print("-" * 72)
    print(f"POOLED (US500+NAS100): {n} OOS trades, win rate {wr:.1%}, "
          f"mean net {mean:+.2f} bps (95% CI [{lo:+.2f}, {hi:+.2f}], t={t:+.2f}), "
          f"stability {stab:.0%}")
    print(f"us_open_orb_indices ROUND 1: {'PASS' if passed else 'FAIL'}")

    with ROUNDS_LOG.open("a") as f:
        f.write(
            f"{datetime.now(timezone.utc).isoformat()} family=us_open_orb_indices "
            f"range=2021-01..2026-06 scheme=500/120xNYopen costs=2.5bpRT "
            f"mean_trade_net_bps={mean:.2f} t={t:.2f} trades={n} win_rate={wr:.2f} "
            f"stability={stab:.2f} result={'PASS' if passed else 'FAIL'}\n"
        )
    print(f"round logged to {ROUNDS_LOG}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
