#!/usr/bin/env python3
"""us_open_orb_indices ROUND 2 (of 2) — volatility-regime conditioned.

Pre-registered direction (reports/orb_research.md): trade only high-vol
opens, where Gao et al. intraday momentum concentrates. Adds vol_pct to the
grid (opening range must clear its trailing-20d quantile). Same universe,
clock, costs, walk-forward, and gate as round 1. THIS DECIDES THE FAMILY.
"""
from __future__ import annotations
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
from scipy import stats
from hft.strategies.orb import walk_forward_orb, GRID_R2

ROOT = Path(__file__).resolve().parents[1]
BARS_DIR = ROOT / "data" / "bars" / "histdata"
ROUNDS_LOG = ROOT / "reports" / "rounds.log"
SYMBOLS = {"US500": "SPXUSD", "NAS100": "NSXUSD"}

def main() -> int:
    all_trades, all_windows = [], []
    for label, stem in SYMBOLS.items():
        files = sorted(BARS_DIR.glob(f"{stem}_M1_*.parquet"))
        m1 = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
        windows, trades = walk_forward_orb(m1, label, grid=GRID_R2)
        nets = np.array([t.net_bps for t in trades])
        wr = float((nets > 0).mean()) if len(nets) else 0.0
        print(f"{label}: {len(windows)} windows, {len(trades)} OOS trades, "
              f"win rate {wr:.0%}, mean net {nets.mean() if len(nets) else 0:+.2f} bps")
        for w in windows:
            print(f"    {w.test_start} {w.params} test_net={w.test_net:+.0f}bps ({w.test_trades} trades)")
        all_trades.extend(trades); all_windows.extend(windows)
    nets = np.array([t.net_bps for t in all_trades])
    n = len(nets)
    if n < 2:
        print("insufficient OOS trades -> FAIL"); return 1
    mean = float(nets.mean())
    t = float(mean / (nets.std(ddof=1) / np.sqrt(n))) if nets.std(ddof=1) > 0 else 0.0
    lo, hi = stats.t.interval(0.95, df=n-1, loc=mean, scale=nets.std(ddof=1)/np.sqrt(n))
    stab = sum(1 for w in all_windows if w.test_trades > 0 and w.test_net > 0) / len(all_windows)
    wr = float((nets > 0).mean())
    passed = n >= 100 and mean > 0 and t >= 2.0 and stab >= 0.6
    print("-" * 72)
    print(f"POOLED: {n} OOS trades, win rate {wr:.1%}, mean net {mean:+.2f} bps "
          f"(95% CI [{lo:+.2f}, {hi:+.2f}], t={t:+.2f}), stability {stab:.0%}")
    print(f"us_open_orb_indices ROUND 2: {'PASS' if passed else 'FAIL — family dead (2 of 2)'}")
    with ROUNDS_LOG.open("a") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat()} family=us_open_orb_vol_conditioned "
                f"range=2021-01..2026-06 scheme=500/120xNYopen costs=2.5bpRT "
                f"mean_trade_net_bps={mean:.2f} t={t:.2f} trades={n} win_rate={wr:.2f} "
                f"stability={stab:.2f} result={'PASS' if passed else 'FAIL-family-dead'}\n")
    print(f"round logged to {ROUNDS_LOG}")
    return 0 if passed else 1

if __name__ == "__main__":
    raise SystemExit(main())
