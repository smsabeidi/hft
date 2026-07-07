#!/usr/bin/env python3
"""C1c — funding-capture symbol expansion to SOL/XRP (research doc §5, C1c).

Hypothesis: alt perps carry richer funding than BTC/ETH; the same hysteresis
state machine captures it after costs even with the thinner books priced in.

Scope note: this round decides whether SOL+XRP join the POOL as additional
capacity. It does not touch the running BTC/ETH parameterization.

PRE-REGISTERED GATE (written before the run):
Pooled SOL+XRP walk-forward OOS, same 2190/548 scheme and grid as round 1,
with costs bumped to 35bp RT (vs 25bp for BTC/ETH — wider spreads and more
slippage on all four legs in thinner books; utilization unchanged at 0.6).
Standard episode gate must hold on the SOL+XRP pool alone:
  >=30 episodes, mean episode net > 0, t >= 2.0, window stability >= 0.6.
FAIL means alts stay out; no cost-assumption shopping after the fact.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from scipy import stats

from hft.crypto.funding_capture import CaptureParams, walk_forward_capture

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "funding"
ROUNDS_LOG = Path(__file__).resolve().parents[1] / "reports" / "rounds.log"
SYMBOLS = ["SOLUSDT", "XRPUSDT"]

GRID = {"enter_bps": [0.3, 0.5, 1.0], "exit_bps": [0.0, 0.2], "smooth_n": [3, 9]}
TRAIN_N, TEST_N = 2190, 548
BASE = CaptureParams(fee_rt_bps=35.0, utilization=0.6)


def main() -> int:
    all_eps, all_windows = [], []
    for sym in SYMBOLS:
        path = DATA_DIR / f"{sym}_funding.parquet"
        if not path.exists():
            print(f"{sym}: no funding data (run scripts/fetch_funding_binance.py)")
            continue
        funding = pd.read_parquet(path)
        res = walk_forward_capture(funding, GRID, TRAIN_N, TEST_N, base=BASE)
        g = res.gate()
        print(f"{sym}: {len(res.windows)} windows, {g['episodes']} OOS episodes, "
              f"mean episode net {g['mean_episode_net']*1e4:.1f} bps, t={g['t']:.2f}, "
              f"stability {g['stability']:.0%}")
        for w in res.windows:
            print(f"    {w.test_start.date()}  {w.params}  "
                  f"train_ann={w.train_annualized:.1%}  test_ann={w.test_annualized:.1%}  "
                  f"({w.test_episodes} episodes)")
        all_eps.extend(res.oos_episodes)
        all_windows.extend(res.windows)

    if not all_eps:
        print("no OOS episodes -> FAIL")
        return 1

    rets = np.array([e.net_return for e in all_eps])
    n = len(rets)
    mean = float(rets.mean())
    t = float(mean / (rets.std(ddof=1) / np.sqrt(n))) if n > 1 and rets.std(ddof=1) > 0 else 0.0
    lo, hi = stats.t.interval(0.95, df=n - 1, loc=mean, scale=rets.std(ddof=1) / np.sqrt(n))
    stability = sum(
        1 for w in all_windows if w.test_episodes > 0 and w.test_annualized > 0
    ) / len(all_windows)
    ann = [w.test_annualized for w in all_windows]
    passed = n >= 30 and mean > 0 and t >= 2.0 and stability >= 0.6

    print("-" * 70)
    print(f"POOLED ({'+'.join(SYMBOLS)}): {n} OOS episodes, "
          f"mean episode net {mean*1e4:.1f} bps (95% CI [{lo*1e4:.1f}, {hi*1e4:.1f}], t={t:.2f})")
    print(f"window stability {stability:.0%} | mean OOS annualized across windows "
          f"{np.mean(ann):.2%}/yr | median {np.median(ann):.2%}/yr")
    print(f"C1c GATE: {'PASS — alts add capacity' if passed else 'FAIL — alts stay out'}")

    with ROUNDS_LOG.open("a") as f:
        f.write(
            f"{datetime.now(timezone.utc).isoformat()} family=funding_capture_altsyms "
            f"range=2021-01..2026-06 scheme={TRAIN_N}/{TEST_N}x8h costs=35bpRT/0.6util "
            f"mean_ep_net_bps={mean*1e4:.1f} t={t:.2f} episodes={n} "
            f"stability={stability:.2f} result={'PASS' if passed else 'FAIL'}\n"
        )
    print(f"round logged to {ROUNDS_LOG}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
