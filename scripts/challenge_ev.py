#!/usr/bin/env python3
"""Business gate calculator: should this strategy attempt a paid evaluation?

Feed it the OOS statistics from a PASSING walk-forward round; it Monte-Carlos
the evaluation under the firm's rules and prices the attempt.

Usage:
    python3 scripts/challenge_ev.py --expectancy 8.0 --std 120 --trades-per-day 3 \
        --balance 50000 --fee 345
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hft.backtest.montecarlo import ChallengeParams, simulate_challenge


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--expectancy", type=float, required=True, help="OOS $/trade")
    ap.add_argument("--std", type=float, required=True, help="OOS per-trade std, $")
    ap.add_argument("--trades-per-day", type=float, default=3.0)
    ap.add_argument("--balance", type=float, default=50_000.0)
    ap.add_argument("--target", type=float, default=0.10)
    ap.add_argument("--daily", type=float, default=0.05)
    ap.add_argument("--total", type=float, default=0.10)
    ap.add_argument("--fee", type=float, default=345.0)
    ap.add_argument("--sims", type=int, default=5_000)
    args = ap.parse_args()

    params = ChallengeParams(
        initial_balance=args.balance,
        profit_target_frac=args.target,
        daily_loss_frac=args.daily,
        total_dd_frac=args.total,
        trades_per_day=args.trades_per_day,
        fee_usd=args.fee,
    )
    res = simulate_challenge(args.expectancy, args.std, params, n_sims=args.sims)
    print(res.summary(args.fee))
    print()
    if res.p_pass >= 0.5:
        print("VERDICT: attempt is defensible IF the walk-forward round truly passed "
              "(>=100 OOS trades, t>=2). Remember: max 2 paid attempts, ever.")
    else:
        print("VERDICT: do not pay the fee. Improve the strategy or the stats first — "
              "a sub-50% pass probability burns the 2-attempt budget on coin flips.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
