"""Conditional funding capture — crypto track, FAMILY #1.

Position: delta-neutral (long spot / short perp, equal notional). While on,
each 8h funding interval pays funding_rate x deployed notional. The strategy
is WHEN to be on: a hysteresis state machine on smoothed funding.

Rules:
- smooth = trailing mean of the last smooth_n funding rates (completed
  intervals only — the rate used to decide interval i is known at its start).
- Enter (turn position on) when smooth > enter_bps. Exit when smooth < exit_bps.
  enter_bps > exit_bps gives hysteresis: no flapping on noise.
- Costs: fee_rt_bps per episode round trip (4 legs: spot in/out, perp in/out),
  charged half at entry, half at exit. utilization is the fraction of capital
  actually deployed as notional (spot leg + perp margin can't exceed capital).

Honest deviations from the forex gate, documented:
- The trade unit is an EPISODE (one entry->exit), which spans days-weeks.
  100 episodes is unreachable in 5.5 years; the gate here requires >=30
  pooled OOS episodes instead, everything else unchanged (expectancy > 0,
  t >= 2 on episode returns, window stability >= 60%).
- Interval pnls are autocorrelated (the position persists), so t-stats are
  computed on episode returns, not interval returns.
- Not modeled: basis convergence P&L (usually favorable when entering on
  high funding — omitting it is conservative), spot borrow (none: own
  capital), venue failure (not modelable; it is the real tail risk).
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import numpy as np
import pandas as pd
from scipy import stats

INTERVALS_PER_YEAR = 3 * 365  # 8h funding


@dataclass(frozen=True)
class CaptureParams:
    enter_bps: float = 0.5   # per 8h interval, on the smoothed rate
    exit_bps: float = 0.0
    smooth_n: int = 3
    fee_rt_bps: float = 25.0  # 4 taker legs, conservative
    utilization: float = 0.6  # fraction of capital deployed as notional


@dataclass
class Episode:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    intervals: int
    gross_return: float  # fraction of capital
    net_return: float


@dataclass
class CaptureResult:
    episodes: list[Episode]
    net_return: float            # total, fraction of capital
    years: float
    time_in_market: float

    @property
    def annualized_net(self) -> float:
        return self.net_return / self.years if self.years > 0 else 0.0


def backtest_capture(funding: pd.DataFrame, p: CaptureParams) -> CaptureResult:
    """funding: columns time, rate (per interval). Decisions use only
    completed intervals: the smoothed value available at interval i excludes
    interval i itself."""
    rates = funding["rate"].to_numpy(dtype=float)
    times = funding["time"].reset_index(drop=True)
    n = len(rates)
    smooth = pd.Series(rates).rolling(p.smooth_n).mean().shift(1).to_numpy()

    enter, exit_ = p.enter_bps / 1e4, p.exit_bps / 1e4
    fee_half = (p.fee_rt_bps / 1e4) / 2 * p.utilization

    episodes: list[Episode] = []
    on = False
    ep_start = ep_gross = 0.0
    ep_start_i = 0
    total_net = 0.0

    for i in range(n):
        s = smooth[i]
        if np.isnan(s):
            continue
        if not on and s > enter:
            on = True
            ep_start_i = i
            ep_gross = 0.0
            total_net -= fee_half
        if on:
            ep_gross += rates[i] * p.utilization
            leaving = s < exit_ or i == n - 1
            if leaving:
                on = False
                total_net += ep_gross - fee_half
                episodes.append(
                    Episode(
                        entry_time=times.iloc[ep_start_i],
                        exit_time=times.iloc[i],
                        intervals=i - ep_start_i + 1,
                        gross_return=ep_gross,
                        net_return=ep_gross - 2 * fee_half,
                    )
                )

    years = n / INTERVALS_PER_YEAR
    tim = sum(e.intervals for e in episodes) / n if n else 0.0
    return CaptureResult(episodes, total_net, years, tim)


@dataclass
class FundingWindow:
    test_start: pd.Timestamp
    params: dict
    train_annualized: float
    test_annualized: float
    test_episodes: int


@dataclass
class FundingRoundResult:
    windows: list[FundingWindow]
    oos_episodes: list[Episode]

    def gate(self) -> dict:
        eps = self.oos_episodes
        rets = np.array([e.net_return for e in eps]) if eps else np.array([])
        n = len(rets)
        mean = float(rets.mean()) if n else 0.0
        t = float(mean / (rets.std(ddof=1) / np.sqrt(n))) if n > 1 and rets.std(ddof=1) > 0 else 0.0
        ci = (
            stats.t.interval(0.95, df=n - 1, loc=mean, scale=rets.std(ddof=1) / np.sqrt(n))
            if n > 1 and rets.std(ddof=1) > 0
            else (mean, mean)
        )
        traded = [w for w in self.windows]
        stability = (
            sum(1 for w in traded if w.test_episodes > 0 and w.test_annualized > 0) / len(traded)
            if traded
            else 0.0
        )
        passed = n >= 30 and mean > 0 and t >= 2.0 and stability >= 0.6
        return {
            "episodes": n,
            "mean_episode_net": mean,
            "t": t,
            "ci": ci,
            "stability": stability,
            "passed": passed,
        }


def _grid(param_grid: dict) -> list[dict]:
    keys = list(param_grid)
    return [dict(zip(keys, v)) for v in product(*(param_grid[k] for k in keys))]


def walk_forward_capture(
    funding: pd.DataFrame,
    param_grid: dict,
    train_n: int,
    test_n: int,
    base: CaptureParams = CaptureParams(),
) -> FundingRoundResult:
    """Same discipline as the forex walk-forward: optimize on train (by
    annualized net), freeze, evaluate on the next test slice, roll forward."""
    funding = funding.reset_index(drop=True)
    windows: list[FundingWindow] = []
    oos: list[Episode] = []
    start = 0
    while start + train_n + test_n <= len(funding):
        train = funding.iloc[start : start + train_n]
        test = funding.iloc[start + train_n : start + train_n + test_n]

        best, best_ann = None, float("-inf")
        for g in _grid(param_grid):
            params = CaptureParams(**{**base.__dict__, **g})
            r = backtest_capture(train, params)
            if r.annualized_net > best_ann:
                best_ann, best = r.annualized_net, g

        params = CaptureParams(**{**base.__dict__, **best})
        r = backtest_capture(test, params)
        windows.append(
            FundingWindow(
                test_start=test["time"].iloc[0],
                params=best,
                train_annualized=best_ann,
                test_annualized=r.annualized_net,
                test_episodes=len(r.episodes),
            )
        )
        oos.extend(r.episodes)
        start += test_n
    return FundingRoundResult(windows, oos)
