#!/usr/bin/env python3
"""C5 round runner — perp_spot_basis_meanrev (pre-registered family).

Spec, grid, cost model, walk-forward scheme and gate are FROZEN in
reports/m3_preregistration.md; the implementation is hft/crypto/basis_meanrev.py
(built blind, tests on synthetic data only). This runner ENFORCES the
pre-registered data floor: it refuses to run until >= 30 qualifying recorded
days exist (>= 60% minute coverage on all four instruments). The coverage
report publishes alongside any result.

Pairs pooled: BTC (BTC-USDT-SWAP vs BTC-USDT), ETH (ETH-USDT-SWAP vs ETH-USDT).
GATE: >= 100 pooled OOS trades (real side only), mean net > 0, t >= 2.0,
window stability >= 0.6. Two failed rounds kill the family, standing rule.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from scipy import stats

from hft.crypto.basis_meanrev import build_basis_frame, load_books5, walk_forward_c5
from hft.crypto.coverage import c5_floor

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "crypto"
ROUNDS_LOG = ROOT / "reports" / "rounds.log"
PAIRS = [("BTC-USDT-SWAP", "BTC-USDT"), ("ETH-USDT-SWAP", "ETH-USDT")]


def main() -> int:
    floor = c5_floor(DATA_ROOT)
    print(f"C5 data floor: {'MET' if floor.met else 'NOT MET'} — {floor.detail}")
    if not floor.met:
        print("Refusing to run: the pre-registered floor is not met. "
              "This is by design (reports/m3_preregistration.md). "
              "Run scripts/coverage_report.py to watch it accrue.")
        return 2

    all_trades, all_windows = [], []
    for perp_inst, spot_inst in PAIRS:
        frame = build_basis_frame(load_books5(DATA_ROOT, perp_inst), load_books5(DATA_ROOT, spot_inst))
        res = walk_forward_c5(frame)
        g = res.gate()
        print(f"{perp_inst} vs {spot_inst}: {len(res.windows)} windows, {g['trades']} OOS trades, "
              f"mean net {g['mean_net']*1e4:.2f} bps, t={g['t']:.2f}, stability {g['stability']:.0%}")
        for w in res.windows:
            print(f"    {w.test_start}  {w.params}  test_net={w.test_net*1e4:.1f}bps "
                  f"({w.test_trades} trades)")
        all_trades.extend(res.oos_trades)
        all_windows.extend(res.windows)

    nets = np.array([t.net for t in all_trades])
    n = len(nets)
    if n < 2:
        print("insufficient OOS trades -> FAIL")
        return 1
    mean = float(nets.mean())
    t = float(mean / (nets.std(ddof=1) / np.sqrt(n))) if nets.std(ddof=1) > 0 else 0.0
    lo, hi = stats.t.interval(0.95, df=n - 1, loc=mean, scale=nets.std(ddof=1) / np.sqrt(n))
    stability = sum(1 for w in all_windows if w.test_trades > 0 and w.test_net > 0) / len(all_windows)
    passed = n >= 100 and mean > 0 and t >= 2.0 and stability >= 0.6

    print("-" * 70)
    print(f"POOLED: {n} OOS trades, mean net {mean*1e4:.2f} bps "
          f"(95% CI [{lo*1e4:.2f}, {hi*1e4:.2f}], t={t:.2f}), stability {stability:.0%}")
    print(f"C5 GATE: {'PASS' if passed else 'FAIL'}")

    with ROUNDS_LOG.open("a") as f:
        f.write(
            f"{datetime.now(timezone.utc).isoformat()} family=basis_meanrev_c5 "
            f"range=recorded scheme=10d/5d costs=25bpRT+measured_spreads "
            f"mean_trade_net_bps={mean*1e4:.2f} t={t:.2f} trades={n} "
            f"stability={stability:.2f} result={'PASS' if passed else 'FAIL'}\n"
        )
    print(f"round logged to {ROUNDS_LOG}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
