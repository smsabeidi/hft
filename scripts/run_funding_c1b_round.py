#!/usr/bin/env python3
"""C1b — funding-persistence conditioning (research doc §5, candidate C1b).

Hypothesis: funding is strongly autocorrelated; an AR(1) one-step forecast of
the next funding rate, used as the entry/exit signal in the SAME hysteresis
state machine, improves capture over the plain trailing-mean signal.

This is a RE-TUNE of the funding_capture family (same entry hypothesis: be on
when expected funding is high), not a new family, per the design doc's family
definition. It therefore does not consume one of the family's 2 rounds; it
either improves the running parameterization or is discarded.

PRE-REGISTERED GATE (written before the run):
The AR(1) variant REPLACES the sma baseline only if ALL hold on pooled
BTC+ETH walk-forward OOS (same 2190/548 scheme, same costs as round 1):
  1. standard episode gate: >=30 episodes, mean net > 0, t >= 2, stability >= 0.6
  2. pooled mean episode net  >  baseline's pooled mean episode net
  3. mean OOS annualized net across windows  >  baseline's
Anything less = FAIL: baseline stands, result logged, no re-tuning beyond
this pre-registered grid (enter x exit identical to round 1's; ar_window in
{45, 90, 180} intervals = 15/30/60 days).
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from hft.crypto.funding_capture import (
    ar1_signal,
    walk_forward_capture,
    walk_forward_signal_capture,
)

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "funding"
ROUNDS_LOG = Path(__file__).resolve().parents[1] / "reports" / "rounds.log"
SYMBOLS = ["BTCUSDT", "ETHUSDT"]

BASE_GRID = {"enter_bps": [0.3, 0.5, 1.0], "exit_bps": [0.0, 0.2], "smooth_n": [3, 9]}
ENTER_GRID = [0.3, 0.5, 1.0]
EXIT_GRID = [0.0, 0.2]
AR_WINDOWS = [45, 90, 180]
TRAIN_N, TEST_N = 2190, 548


def pooled_stats(episodes, windows):
    rets = np.array([e.net_return for e in episodes])
    n = len(rets)
    mean = float(rets.mean()) if n else 0.0
    t = float(mean / (rets.std(ddof=1) / np.sqrt(n))) if n > 1 and rets.std(ddof=1) > 0 else 0.0
    stability = (
        sum(1 for w in windows if w.test_episodes > 0 and w.test_annualized > 0) / len(windows)
        if windows else 0.0
    )
    mean_ann = float(np.mean([w.test_annualized for w in windows])) if windows else 0.0
    return n, mean, t, stability, mean_ann


def main() -> int:
    base_eps, base_win, var_eps, var_win = [], [], [], []
    for sym in SYMBOLS:
        path = DATA_DIR / f"{sym}_funding.parquet"
        if not path.exists():
            print(f"{sym}: no funding data (run scripts/fetch_funding_binance.py)")
            continue
        funding = pd.read_parquet(path)

        b = walk_forward_capture(funding, BASE_GRID, TRAIN_N, TEST_N)
        base_eps.extend(b.oos_episodes)
        base_win.extend(b.windows)

        signals = {f"ar1_{w}": ar1_signal(funding["rate"], w) for w in AR_WINDOWS}
        v = walk_forward_signal_capture(funding, signals, ENTER_GRID, EXIT_GRID, TRAIN_N, TEST_N)
        var_eps.extend(v.oos_episodes)
        var_win.extend(v.windows)
        print(f"{sym}: baseline {len(b.oos_episodes)} eps | ar1 {len(v.oos_episodes)} eps")
        for w in v.windows:
            print(f"    {w.test_start.date()}  {w.params}  test_ann={w.test_annualized:.2%} "
                  f"({w.test_episodes} eps)")

    if not var_eps:
        print("no variant OOS episodes -> FAIL")
        return 1

    bn, bmean, bt, bstab, bann = pooled_stats(base_eps, base_win)
    vn, vmean, vt, vstab, vann = pooled_stats(var_eps, var_win)
    print("-" * 70)
    print(f"baseline (sma): {bn} eps, mean {bmean*1e4:.1f} bps, t={bt:.2f}, "
          f"stab {bstab:.0%}, mean ann {bann:.2%}/yr")
    print(f"variant (ar1):  {vn} eps, mean {vmean*1e4:.1f} bps, t={vt:.2f}, "
          f"stab {vstab:.0%}, mean ann {vann:.2%}/yr")

    gate1 = vn >= 30 and vmean > 0 and vt >= 2.0 and vstab >= 0.6
    gate2 = vmean > bmean
    gate3 = vann > bann
    passed = gate1 and gate2 and gate3
    for label, ok in [("episode gate", gate1),
                      ("beats baseline mean episode net", gate2),
                      ("beats baseline mean annualized", gate3)]:
        print(f"  [{'x' if ok else ' '}] {label}")
    print(f"C1b GATE: {'PASS — ar1 replaces sma' if passed else 'FAIL — sma baseline stands'}")

    with ROUNDS_LOG.open("a") as f:
        f.write(
            f"{datetime.now(timezone.utc).isoformat()} family=funding_capture_ar1_retune "
            f"range=2021-01..2026-06 scheme={TRAIN_N}/{TEST_N}x8h costs=25bpRT/0.6util "
            f"mean_ep_net_bps={vmean*1e4:.1f} t={vt:.2f} episodes={vn} stability={vstab:.2f} "
            f"baseline_bps={bmean*1e4:.1f} result={'PASS' if passed else 'FAIL'}\n"
        )
    print(f"round logged to {ROUNDS_LOG}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
