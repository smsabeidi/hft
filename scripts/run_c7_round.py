#!/usr/bin/env python3
"""C7 round — fx_carry_vol_filtered (pre-registered; founder green-lit the
forex fork reopening 2026-07-07).

Spec and gate are FROZEN in reports/c7_preregistration.md:
- pairs EURUSD/GBPUSD/AUDUSD, daily bars (22:00 UTC boundary) from histdata
- causal rate-differential signal (FRED legs, monthly ffill), grid
  thresh in {0,50,100}bp x vol_q in {none,0.80}
- swap markup scenarios m in {0.5, 1.0, 1.5}%/yr; GATE AT m=1.0 ONLY
- walk-forward 500/120 daily rolled 120, optimize by after-cost train net
- GATE: >=20 pooled OOS episodes, mean episode net > 0, t >= 2.0,
  window stability >= 0.6. Two failed rounds kill the family.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from scipy import stats

from hft.strategies.carry import PAIRS, daily_bars_from_m1, build_pair_frame, load_rates, walk_forward_carry

ROOT = Path(__file__).resolve().parents[1]
BARS_DIR = ROOT / "data" / "bars" / "histdata"
RATES_DIR = ROOT / "data" / "rates"
ROUNDS_LOG = ROOT / "reports" / "rounds.log"
MARKUPS = [0.5, 1.0, 1.5]
GATE_MARKUP = 1.0


def load_pair(pair: str) -> pd.DataFrame:
    files = sorted(BARS_DIR.glob(f"{pair}_M1_*.parquet"))
    m1 = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True).sort_values("time")
    return daily_bars_from_m1(m1)


def main() -> int:
    rates = load_rates(RATES_DIR)
    frames = {p: build_pair_frame(load_pair(p), rates, ccy) for p, ccy in PAIRS.items()}

    gate_stats = None
    for m in MARKUPS:
        eps, wins = [], []
        for pair, frame in frames.items():
            w, e = walk_forward_carry(frame, pair, markup_pct=m)
            wins.extend(w)
            eps.extend(e)
            if m == GATE_MARKUP:
                for x in w:
                    print(f"    {pair} {x.test_start} {x.params} "
                          f"test_net={x.test_net*1e4:+.0f}bp ({x.test_episodes} eps)")
        nets = np.array([e.net_return for e in eps])
        n = len(nets)
        mean = float(nets.mean()) if n else 0.0
        t = float(mean / (nets.std(ddof=1) / np.sqrt(n))) if n > 1 and nets.std(ddof=1) > 0 else 0.0
        stab = (sum(1 for w in wins if w.test_episodes > 0 and w.test_net > 0) / len(wins)
                if wins else 0.0)
        tag = "GATE" if m == GATE_MARKUP else "info"
        print(f"[{tag}] markup {m:.1f}%/yr: {n} episodes, mean {mean*1e4:+.0f}bp, "
              f"t={t:+.2f}, stability {stab:.0%}")
        if m == GATE_MARKUP:
            lo, hi = (stats.t.interval(0.95, df=n - 1, loc=mean,
                                       scale=nets.std(ddof=1) / np.sqrt(n))
                      if n > 1 and nets.std(ddof=1) > 0 else (mean, mean))
            passed = n >= 20 and mean > 0 and t >= 2.0 and stab >= 0.6
            gate_stats = (n, mean, t, stab, lo, hi, passed)

    n, mean, t, stab, lo, hi, passed = gate_stats
    print("-" * 72)
    print(f"C7 GATE (m={GATE_MARKUP}%): {n} pooled OOS episodes, "
          f"mean {mean*1e4:+.0f}bp (95% CI [{lo*1e4:+.0f}, {hi*1e4:+.0f}]), "
          f"t={t:+.2f}, stability {stab:.0%}")
    print(f"RESULT: {'PASS' if passed else 'FAIL'}")

    with ROUNDS_LOG.open("a") as f:
        f.write(
            f"{datetime.now(timezone.utc).isoformat()} family=fx_carry_vol_filtered "
            f"range=2021-01..2026-06 scheme=500/120x1d costs=1.8pipRT+swap_markup1.0 "
            f"mean_ep_net_bps={mean*1e4:.1f} t={t:.2f} episodes={n} "
            f"stability={stab:.2f} result={'PASS' if passed else 'FAIL'}\n"
        )
    print(f"round logged to {ROUNDS_LOG}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
