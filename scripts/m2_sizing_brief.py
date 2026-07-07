#!/usr/bin/env python3
"""Fee-tier sensitivity + M2 sizing arithmetic for the funding book.

The institutional optimization pass, done the way desks actually do it:
no signal re-tuning (C1b already showed the baseline wins; C5/C6 are
pre-registered and untouchable). Two things only:

1. FEE SENSITIVITY — pure arithmetic on the round-1 pooled OOS episode set.
   Episode gross is fee-independent; net = gross - fee_rt x utilization.
   Recomputing nets under real OKX fee tiers prices the cheapest genuine
   "alpha" available: execution style and fee tier. Zero re-optimization —
   the episodes are exactly the round-1 walk-forward output.

2. M2 SIZING — Kelly and empirical-loss arithmetic for the founder's $1-5k
   decision. Episode returns are fractions of capital; Kelly leverage
   f* = mean/variance. A regime scenario scales the mean to the Kraken
   transfer-test level (+19.6bps vs +74.2) per the M1.5 read.

Decision support for the founder; not investment advice. Numbers inform the
M2 rung whose kill criteria are already fixed in the scaling roadmap.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from hft.crypto.funding_capture import walk_forward_capture

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "funding"
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
GRID = {"enter_bps": [0.3, 0.5, 1.0], "exit_bps": [0.0, 0.2], "smooth_n": [3, 9]}
TRAIN_N, TEST_N = 2190, 548
UTIL = 0.6
ASSUMED_FEE = 25.0

# OKX-style tiers, bps round trip across the 4 legs (2 spot + 2 perp);
# re-verify on the venue's fee page at M2 time.
FEE_TIERS = {
    "taker tier-0 (worst case)": 30.0,
    "round-1 assumption": 25.0,
    "maker tier-0 (post-only entries)": 20.0,
    "maker VIP-ish (volume/fee promos)": 14.0,
}

KRAKEN_REGIME_MEAN_BPS = 19.6  # M1.5 transfer test, trailing-1y regime


def main() -> int:
    eps = []
    for sym in SYMBOLS:
        funding = pd.read_parquet(DATA_DIR / f"{sym}_funding.parquet")
        eps.extend(walk_forward_capture(funding, GRID, TRAIN_N, TEST_N).oos_episodes)
    nets = np.array([e.net_return for e in eps])           # at 25bp RT assumed
    gross = nets + (ASSUMED_FEE / 1e4) * UTIL              # fee-independent
    span_years = (max(e.exit_time for e in eps) - min(e.entry_time for e in eps)).days / 365.25
    eps_per_year = len(eps) / span_years

    print(f"round-1 pooled OOS: {len(eps)} episodes over {span_years:.1f}y "
          f"({eps_per_year:.1f} episodes/yr)")
    print("-" * 72)
    print("FEE SENSITIVITY (same episodes, arithmetic only):")
    base_ann = None
    for label, fee in FEE_TIERS.items():
        n = gross - (fee / 1e4) * UTIL
        ann = n.mean() * eps_per_year
        if fee == ASSUMED_FEE:
            base_ann = ann
        print(f"  {label:36s} fee {fee:>4.0f}bp -> mean ep {n.mean()*1e4:+6.1f}bp, "
              f"~{ann:.2%}/yr, P(ep<0) {float((n < 0).mean()):.0%}")
    uplift = None
    maker_net = gross - (20.0 / 1e4) * UTIL
    uplift = (maker_net.mean() * eps_per_year - base_ann) / abs(base_ann)
    print(f"  -> post-only entries alone are worth ~{uplift:+.0%} of the book's "
          "annual return, for zero new risk. This is the cheapest alpha that exists.")

    print("-" * 72)
    print("M2 SIZING (Kelly + empirical losses):")
    for label, mean_scale in [("round-1 regime (74.2bp mean)", 1.0),
                              ("Kraken 1y regime (19.6bp mean)",
                               KRAKEN_REGIME_MEAN_BPS / (nets.mean() * 1e4))]:
        m = nets.mean() * mean_scale
        v = nets.var(ddof=1)
        kelly = m / v if v > 0 else float("inf")
        shifted = nets - nets.mean() + m
        print(f"  {label}:")
        print(f"    mean ep {m*1e4:+.1f}bp, sd {np.sqrt(v)*1e4:.1f}bp, "
              f"Kelly leverage f* = {kelly:.1f}x")
        print(f"    P(episode < 0) = {float((shifted < 0).mean()):.0%}, "
              f"worst episode {shifted.min()*1e4:+.1f}bp, "
              f"~{m * eps_per_year:.2%}/yr at 1x")
    print("-" * 72)
    print("reading: Kelly does NOT bind (f* >> 1) — variance is not the risk here.")
    print("The binding constraints are venue/counterparty tail risk and the M2")
    print("objective (verify live ops, slippage-vs-model, accounting), which argue")
    print("for the SMALL end of $1-5k regardless of Kelly. Expected P&L at this")
    print("size is beer money by design; M2 buys verified operations, not income.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
