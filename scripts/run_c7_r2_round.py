#!/usr/bin/env python3
"""fx_carry round 2 (of 2) — cross-sectional carry. The family is decided here.

Spec frozen as the dated amendment in reports/c7_preregistration.md BEFORE
any cross-sectional analysis: 7 currencies vs USD, weekly Friday rebalance,
long top-k / short bottom-k, retail swap markup on gross (GATE at 1.0%/yr),
0.85bp/side turnover, 500/120 walk-forward, gate on pooled OOS weekly
returns (>=100 obs, mean > 0, t >= 2, stability >= 0.6).
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from scipy import stats

from hft.strategies.carry_xs import build_panel, walk_forward_xs

ROOT = Path(__file__).resolve().parents[1]
BARS_DIR = ROOT / "data" / "bars" / "histdata"
RATES_DIR = ROOT / "data" / "rates"
ROUNDS_LOG = ROOT / "reports" / "rounds.log"
MARKUPS = [0.5, 1.0, 1.5]
GATE_M = 1.0


def main() -> int:
    panel = build_panel(BARS_DIR, RATES_DIR)
    ccys = sorted(c.split("_", 1)[1] for c in panel.columns if c.startswith("ret_"))
    print(f"panel: {len(panel)} trading days, currencies: {','.join(ccys)}")

    gate = None
    for m in MARKUPS:
        windows, weekly = walk_forward_xs(panel, markup_pct=m)
        n = len(weekly)
        mean = float(weekly.mean()) if n else 0.0
        t = float(mean / (weekly.std(ddof=1) / np.sqrt(n))) if n > 1 and weekly.std(ddof=1) > 0 else 0.0
        stab = (sum(1 for w in windows if w.test_weeks > 0 and w.test_net > 0) / len(windows)
                if windows else 0.0)
        ann = mean * 52
        tag = "GATE" if m == GATE_M else "info"
        print(f"[{tag}] markup {m:.1f}%/yr: {n} OOS weeks, mean {mean*1e4:+.1f} bps/wk "
              f"(~{ann:+.2%}/yr), t={t:+.2f}, stability {stab:.0%}")
        if m == GATE_M:
            for w in windows:
                print(f"    {w.test_start} {w.params} test_net={w.test_net*1e4:+.0f}bps "
                      f"({w.test_weeks} wks)")
            lo, hi = (stats.t.interval(0.95, df=n - 1, loc=mean,
                                       scale=weekly.std(ddof=1) / np.sqrt(n))
                      if n > 1 else (mean, mean))
            passed = n >= 100 and mean > 0 and t >= 2.0 and stab >= 0.6
            gate = (n, mean, t, stab, lo, hi, passed)

    n, mean, t, stab, lo, hi, passed = gate
    print("-" * 72)
    print(f"fx_carry_xs GATE (m={GATE_M}%): {n} OOS weeks, mean {mean*1e4:+.1f} bps/wk "
          f"(95% CI [{lo*1e4:+.1f}, {hi*1e4:+.1f}]), t={t:+.2f}, stability {stab:.0%}")
    print(f"ROUND 2 RESULT: {'PASS — family enters the pipeline' if passed else 'FAIL — fx_carry family DEAD (2 of 2)'}")

    with ROUNDS_LOG.open("a") as f:
        f.write(
            f"{datetime.now(timezone.utc).isoformat()} family=fx_carry_xs_r2 "
            f"range=2021-01..2026-06 scheme=500/120x1d-weekly costs=0.85bp_side+markup1.0 "
            f"mean_week_net_bps={mean*1e4:.1f} t={t:.2f} weeks={n} "
            f"stability={stab:.2f} result={'PASS' if passed else 'FAIL-family-dead'}\n"
        )
    print(f"round logged to {ROUNDS_LOG}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
