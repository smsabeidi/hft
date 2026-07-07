#!/usr/bin/env python3
"""fvg_retest ROUND 2 (of 2) — XAUUSD + BTCUSD. The family is decided here.

Spec, grids, and per-symbol friendly-floor costs are FROZEN in
hft/strategies/fvg_rel.py (written before this run). Round 1 (FX) found a
real signal (t=+2.70) an eighth the size of costs; this round asks the only
remaining honest question: does the same imbalance-retest signal clear costs
on the big-range flagship instruments? After this run the family PASSES into
the pipeline or dies under the standing 2-round rule — no round 3.

GATE (at friendly costs XAU 2bp / BTC 10bp RT): pooled >= 100 OOS trades,
mean net > 0 bps, t >= 2.0, stability >= 0.6.
Conservative panel (XAU 4bp / BTC 15bp) reported non-gating.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from scipy import stats

from hft.strategies.fvg_rel import walk_forward_fvg_rel

ROOT = Path(__file__).resolve().parents[1]
ROUNDS_LOG = ROOT / "reports" / "rounds.log"

SYMBOLS = {
    # symbol: (glob dir, glob pattern, friendly cost bps RT, conservative bps RT)
    "XAUUSD": (ROOT / "data" / "bars" / "histdata", "XAUUSD_M1_*.parquet", 2.0, 4.0),
    "BTCUSD": (ROOT / "data" / "bars" / "binance", "BTCUSDT-1m-*.parquet", 10.0, 15.0),
}


def main() -> int:
    pooled = []   # (gross_bps, friendly_cost, conservative_cost)
    all_windows = []
    for sym, (d, pattern, cost_f, cost_c) in SYMBOLS.items():
        files = sorted(d.glob(pattern))
        if not files:
            print(f"{sym}: NO DATA ({d}/{pattern}) — cannot run")
            return 1
        m1 = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
        windows, trades = walk_forward_fvg_rel(m1, sym, cost_rt_bps=cost_f)
        nets = np.array([t.gross_bps - cost_f for t in trades])
        wr = float((nets > 0).mean()) if len(nets) else 0.0
        print(f"{sym}: {len(windows)} windows, {len(trades)} OOS trades, "
              f"win rate {wr:.0%}, mean net {nets.mean() if len(nets) else 0:+.2f} bps "
              f"@ {cost_f:.0f}bp RT")
        for w in windows:
            print(f"    {w.test_start} {w.params} test_net={w.test_net:+.0f}bps "
                  f"({w.test_trades} trades)")
        pooled.extend((t.gross_bps, cost_f, cost_c) for t in trades)
        all_windows.extend(windows)

    gross = np.array([g for g, _, _ in pooled])
    nets_f = np.array([g - cf for g, cf, _ in pooled])
    nets_c = np.array([g - cc for g, _, cc in pooled])
    n = len(nets_f)
    if n < 2:
        print("insufficient OOS trades -> FAIL")
        return 1

    def stats_line(x):
        m = float(x.mean())
        t = float(m / (x.std(ddof=1) / np.sqrt(len(x)))) if x.std(ddof=1) > 0 else 0.0
        return m, t

    mean_f, t_f = stats_line(nets_f)
    mean_c, t_c = stats_line(nets_c)
    lo, hi = stats.t.interval(0.95, df=n - 1, loc=mean_f, scale=nets_f.std(ddof=1) / np.sqrt(n))
    stab = sum(1 for w in all_windows if w.test_trades > 0 and w.test_net > 0) / len(all_windows)
    wr = float((nets_f > 0).mean())
    passed = n >= 100 and mean_f > 0 and t_f >= 2.0 and stab >= 0.6

    print("-" * 72)
    print(f"POOLED (XAU+BTC): {n} OOS trades, win rate {wr:.1%}")
    print(f"  friendly costs:     mean {mean_f:+.2f} bps (95% CI [{lo:+.2f}, {hi:+.2f}], "
          f"t={t_f:+.2f}), stability {stab:.0%}   <- GATE")
    print(f"  conservative costs: mean {mean_c:+.2f} bps (t={t_c:+.2f})   [non-gating]")
    print(f"fvg_retest ROUND 2 GATE: {'PASS' if passed else 'FAIL'} — "
          f"{'family enters the pipeline' if passed else 'family DEAD (2 of 2 rounds consumed)'}")

    with ROUNDS_LOG.open("a") as f:
        f.write(
            f"{datetime.now(timezone.utc).isoformat()} family=fvg_retest_r2_gold_btc "
            f"range=2021-01..2026-06 scheme=500/120xM5 costs=XAU2bp/BTC10bpRT "
            f"mean_trade_net_bps={mean_f:.2f} t={t_f:.2f} trades={n} win_rate={wr:.2f} "
            f"stability={stab:.2f} result={'PASS' if passed else 'FAIL-family-dead'}\n"
        )
    print(f"round logged to {ROUNDS_LOG}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
