#!/usr/bin/env python3
"""Evaluation-pass mathematics — calibrating Dollar's risk layer.

THE PROBLEM (first-passage with barriers): a prop evaluation is not "make
money"; it is "touch +A% before touching -B% (static) while never dropping
D% in a day". For a strategy with per-trade edge and volatility, the risk-
per-trade r sets both the drift AND the diffusion of the equity path —
raising r raises the speed toward the target and the odds of busting.
There is an interior optimum, and it is NOT Kelly (Kelly maximizes growth;
an eval maximizes barrier-hitting odds under a hard floor).

METHOD:
1. Closed form (validation): for a driftful Brownian path with per-trade
   mean mu and std sigma, P(hit +A before -B) =
   (1 - exp(-2 mu B / sigma^2)) / (1 - exp(-2 mu (A+B) / sigma^2)).
2. Simulation (the real answer): adds what the closed form cannot hold —
   the DAILY loss rule (nested barrier, resets at day start) and Dollar's
   anti-martingale throttle tiers. The simulator is validated by matching
   the closed form when both extras are disabled; divergence there would
   mean the simulator lies.

Strategy quality is parameterized by annualized Sharpe S at t trades/day:
per-trade edge in R units = S / sqrt(252 t). The founder's verified
FundedNext numbers: target +5, daily -5 (anchored at day start,
conservative), static floor -10, all in % of initial balance.
"""

from __future__ import annotations

import sys

import numpy as np

TARGET, TOTAL_B, DAILY_D = 5.0, 10.0, 5.0     # % of initial balance
HORIZON_DAYS = 60                              # eval horizon (trial itself: ~10)
SIMS = 20_000
THROTTLE = ((0.05, 1.00), (0.08, 0.60), (0.12, 0.35))  # mirrors the engine


def closed_form(mu: float, sigma: float, a: float = TARGET, b: float = TOTAL_B) -> float:
    if abs(mu) < 1e-12:
        return b / (a + b)
    th = 2.0 * mu / (sigma * sigma)
    return (1.0 - np.exp(-th * b)) / (1.0 - np.exp(-th * (a + b)))


def throttle_mult(dd_frac: float) -> float:
    for lim, m in THROTTLE:
        if dd_frac < lim:
            return m
    return 0.0


def simulate(edge_r: float, r_pct: float, tpd: int, use_daily: bool,
             use_throttle: bool, sims: int = SIMS, seed: int = 7) -> dict:
    rng = np.random.default_rng(seed)
    passed = busted = 0
    days_to_pass = []
    for s in range(sims):
        eq, peak, day_anchor = 0.0, 0.0, 0.0
        outcome = None
        for day in range(HORIZON_DAYS):
            day_anchor = eq
            for _ in range(tpd):
                r_eff = r_pct
                if use_throttle:
                    # drawdown fraction vs a 100-unit initial balance + peak
                    r_eff *= throttle_mult((peak - eq) / 100.0)
                    if r_eff <= 0.0:
                        continue
                x = rng.normal(edge_r, 1.0)     # P&L in R units
                eq += r_eff * x
                peak = max(peak, eq)
                if eq >= TARGET:
                    outcome = "pass"
                    break
                if eq <= -TOTAL_B or (use_daily and eq <= day_anchor - DAILY_D):
                    outcome = "bust"
                    break
            if outcome:
                break
        if outcome == "pass":
            passed += 1
            days_to_pass.append(day + 1)
        elif outcome == "bust":
            busted += 1
    return {
        "pass": passed / sims,
        "bust": busted / sims,
        "timeout": 1.0 - (passed + busted) / sims,
        "median_days": float(np.median(days_to_pass)) if days_to_pass else float("nan"),
    }


def main() -> int:
    tpd = 5
    print(f"evaluation-pass odds — target +{TARGET}%, floor -{TOTAL_B}% static, "
          f"daily -{DAILY_D}% (day-start anchor), {tpd} trades/day, "
          f"{HORIZON_DAYS}-day horizon, {SIMS:,} sims/cell")
    print("=" * 78)

    # 1) simulator validation vs closed form (no daily rule, no throttle)
    print("simulator validation (daily+throttle OFF) vs closed-form barrier math:")
    for sharpe in (0.5, 1.0, 2.0):
        edge = sharpe / np.sqrt(252 * tpd)
        for r in (0.5, 1.0):
            sim = simulate(edge, r, tpd, use_daily=False, use_throttle=False)
            cf = closed_form(r * edge, r)
            print(f"  S={sharpe:>3} r={r:.2f}%:  sim {sim['pass']:.3f}  "
                  f"closed-form {cf:.3f}  (|diff| {abs(sim['pass']-cf):.3f})")

    # 2) the real question: full rules + throttle, sweep r
    print("-" * 78)
    print("full rules (daily + throttle ON): pass/bust by risk-per-trade")
    print(f"{'Sharpe':>7} {'r%':>6} {'P(pass)':>8} {'P(bust)':>8} {'P(timeout)':>10} {'med days':>9}")
    best = {}
    for sharpe in (0.5, 1.0, 1.5, 2.0):
        edge = sharpe / np.sqrt(252 * tpd)
        for r in (0.25, 0.5, 0.75, 1.0, 1.5, 2.0):
            out = simulate(edge, r, tpd, use_daily=True, use_throttle=True)
            print(f"{sharpe:>7} {r:>6.2f} {out['pass']:>8.3f} {out['bust']:>8.3f} "
                  f"{out['timeout']:>10.3f} {out['median_days']:>9.1f}")
            key = sharpe
            if key not in best or out["pass"] > best[key][1]:
                best[key] = (r, out["pass"], out["bust"])
        print()
    print("-" * 78)
    print("optimal risk-per-trade by strategy quality (max P(pass)):")
    for s, (r, p, b) in sorted(best.items()):
        print(f"  Sharpe {s:>3}: r* = {r:.2f}%  ->  P(pass) {p:.1%}, P(bust) {b:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
