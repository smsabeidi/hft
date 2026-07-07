#!/usr/bin/env python3
"""fvg_retest round 1 — the founder-directed ICT/SMC class representative.

Spec, grid, costs, and gate are FROZEN in hft/strategies/fvg.py's docstring
(written before this run). Founder direction 2026-07-07 amends the standing
family-scope rule; this round tests FVG retest at the founder's requested
1:3 / 1:4 geometry on M5 formations with M1-resolution fills.

GATE: pooled EURUSD+GBPUSD+AUDUSD OOS >= 100 trades, mean net > 0 pips,
t >= 2.0, window stability >= 0.6, at friendly 1.05 pip RT costs.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from scipy import stats

from hft.strategies.fvg import walk_forward_fvg

ROOT = Path(__file__).resolve().parents[1]
BARS_DIR = ROOT / "data" / "bars" / "histdata"
ROUNDS_LOG = ROOT / "reports" / "rounds.log"
PAIRS = ["EURUSD", "GBPUSD", "AUDUSD"]


def main() -> int:
    all_trades, all_windows = [], []
    for pair in PAIRS:
        files = sorted(BARS_DIR.glob(f"{pair}_M1_*.parquet"))
        m1 = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
        windows, trades = walk_forward_fvg(m1, pair)
        nets = np.array([t.net_pips for t in trades])
        wr = float((nets > 0).mean()) if len(nets) else 0.0
        print(f"{pair}: {len(windows)} windows, {len(trades)} OOS trades, "
              f"win rate {wr:.0%}, mean {nets.mean() if len(nets) else 0:+.2f} pips")
        for w in windows:
            print(f"    {w.test_start} {w.params} test_net={w.test_net:+.0f}p "
                  f"({w.test_trades} trades)")
        all_trades.extend(trades)
        all_windows.extend(windows)

    nets = np.array([t.net_pips for t in all_trades])
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
    print(f"POOLED: {n} OOS trades, win rate {wr:.1%}, mean net {mean:+.2f} pips "
          f"(95% CI [{lo:+.2f}, {hi:+.2f}], t={t:+.2f}), stability {stab:.0%}")
    print(f"fvg_retest GATE: {'PASS' if passed else 'FAIL'}")

    with ROUNDS_LOG.open("a") as f:
        f.write(
            f"{datetime.now(timezone.utc).isoformat()} family=fvg_retest_1to3 "
            f"range=2021-01..2026-06 scheme=500/120xM5 costs=1.05pipRT "
            f"mean_trade_net_pips={mean:.2f} t={t:.2f} trades={n} win_rate={wr:.2f} "
            f"stability={stab:.2f} result={'PASS' if passed else 'FAIL'}\n"
        )
    print(f"round logged to {ROUNDS_LOG}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
