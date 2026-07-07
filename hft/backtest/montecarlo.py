"""Monte Carlo challenge simulator: turns walk-forward trade statistics into
the business decision the design doc's gate 5 actually asks — is this strategy
worth a paid evaluation fee?

Model: trades arrive Poisson(trades_per_day); per-trade net pnl is drawn from
a Student-t (fat tails, df configurable) scaled to the strategy's measured
expectancy and standard deviation. The firm's rules are enforced trade by
trade: daily loss floor (anchor = balance at day start, FTMO-style vs initial
balance), static total drawdown floor, profit target.

Assumptions (documented, deliberate):
- flat overnight (the chosen strategies time-stop; no overnight equity swings)
- iid trades — real pnl is autocorrelated across regimes, so treat results as
  optimistic on the pass side; the min-trading-days rule is checked, and a
  max_days cap marks stalled runs as timeouts (a timeout is not a fail at
  FTMO, but capital sits idle — we count it separately).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ChallengeParams:
    initial_balance: float = 50_000.0
    profit_target_frac: float = 0.10
    daily_loss_frac: float = 0.05
    total_dd_frac: float = 0.10
    min_trading_days: int = 4
    max_days: int = 90
    trades_per_day: float = 3.0
    fee_usd: float = 345.0


@dataclass
class ChallengeResult:
    p_pass: float
    p_daily_breach: float
    p_total_breach: float
    p_timeout: float
    median_days_to_pass: float
    expected_attempts_per_pass: float

    def summary(self, fee_usd: float) -> str:
        cost_per_pass = (
            self.expected_attempts_per_pass * fee_usd if self.p_pass > 0 else float("inf")
        )
        return (
            f"P(pass)={self.p_pass:.1%}  P(daily breach)={self.p_daily_breach:.1%}  "
            f"P(total breach)={self.p_total_breach:.1%}  P(timeout)={self.p_timeout:.1%}\n"
            f"median days to pass: {self.median_days_to_pass:.0f}\n"
            f"expected fee cost per funded account: ${cost_per_pass:,.0f} "
            f"({self.expected_attempts_per_pass:.1f} attempts at ${fee_usd:.0f})"
        )


def simulate_challenge(
    expectancy_usd: float,
    std_usd: float,
    params: ChallengeParams = ChallengeParams(),
    n_sims: int = 5_000,
    seed: int = 0,
    t_df: int = 5,
) -> ChallengeResult:
    if std_usd <= 0:
        raise ValueError("std_usd must be positive")
    rng = np.random.default_rng(seed)
    # scale Student-t to unit variance before applying the strategy's std
    t_scale = np.sqrt((t_df - 2) / t_df)

    target = params.initial_balance * (1 + params.profit_target_frac)
    total_floor = params.initial_balance * (1 - params.total_dd_frac)
    daily_limit = params.daily_loss_frac * params.initial_balance

    passes, daily_breaches, total_breaches, timeouts = 0, 0, 0, 0
    days_to_pass: list[int] = []

    for _ in range(n_sims):
        balance = params.initial_balance
        outcome = "timeout"
        for day in range(1, params.max_days + 1):
            day_anchor = balance
            daily_floor = day_anchor - daily_limit
            n_trades = rng.poisson(params.trades_per_day)
            for _ in range(n_trades):
                pnl = expectancy_usd + std_usd * t_scale * rng.standard_t(t_df)
                balance += pnl
                if balance <= daily_floor:
                    outcome = "daily"
                    break
                if balance <= total_floor:
                    outcome = "total"
                    break
            if outcome in ("daily", "total"):
                break
            if balance >= target and day >= params.min_trading_days:
                outcome = "pass"
                days_to_pass.append(day)
                break
        if outcome == "pass":
            passes += 1
        elif outcome == "daily":
            daily_breaches += 1
        elif outcome == "total":
            total_breaches += 1
        else:
            timeouts += 1

    p_pass = passes / n_sims
    return ChallengeResult(
        p_pass=p_pass,
        p_daily_breach=daily_breaches / n_sims,
        p_total_breach=total_breaches / n_sims,
        p_timeout=timeouts / n_sims,
        median_days_to_pass=float(np.median(days_to_pass)) if days_to_pass else float("nan"),
        expected_attempts_per_pass=(1.0 / p_pass) if p_pass > 0 else float("inf"),
    )
