"""us_open_orb_indices — Opening Range Breakout at the US cash open.

Implements EXACTLY the pre-registration in reports/orb_research.md:
NY-clock session logic (09:30 auction open; DST handled by tz conversion),
opening range of the first R minutes, entry on first M1 close beyond the
range before 12:00 NY, stop at the opposite range edge, optional 4R target,
hard 15:55 NY exit, one trade per instrument per day, 2.5bp RT costs.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import numpy as np
import pandas as pd

COST_RT_BPS = 2.5
GRID = {"range_min": [15, 30], "target_r": [0.0, 4.0]}  # 0.0 = no target
# ROUND 2 (pre-registered direction, reports/orb_research.md): condition on
# the opening-range volatility regime — trade only when the day's opening
# range is large relative to its trailing history, where Gao et al. intraday
# momentum concentrates. vol_pct = 0.0 means unconditioned (round-1 behavior).
GRID_R2 = {"range_min": [15, 30], "target_r": [0.0, 4.0], "vol_pct": [0.5, 0.65]}
VOL_LOOKBACK = 20  # trailing days for the opening-range volatility percentile
TRAIN_N, TEST_N, ROLL_N = 500, 120, 120

OPEN_MIN = 9 * 60 + 30    # 09:30 NY
ENTRY_CUTOFF = 12 * 60    # 12:00 NY
DAY_END = 15 * 60 + 55    # 15:55 NY


@dataclass(frozen=True)
class ORBParams:
    range_min: int = 30
    target_r: float = 0.0
    vol_pct: float = 0.0  # 0.0 = unconditioned; else require the day's opening
                          # range >= this trailing-VOL_LOOKBACK-day quantile


@dataclass
class ORBTrade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    direction: int
    net_bps: float


def prep(m1: pd.DataFrame) -> pd.DataFrame:
    """Attach NY-clock columns. Input times must be tz-aware UTC."""
    ny = m1["time"].dt.tz_convert("America/New_York")
    out = m1.copy()
    out["day"] = ny.dt.date
    out["minute"] = ny.dt.hour * 60 + ny.dt.minute
    return out


def run_orb(m1: pd.DataFrame, p: ORBParams) -> list[ORBTrade]:
    trades: list[ORBTrade] = []
    recent_ranges: list[float] = []   # trailing opening-range sizes (bps), causal
    for _, day_rows in m1.groupby("day", sort=True):
        d = day_rows[day_rows["minute"] >= OPEN_MIN]
        rng = d[d["minute"] < OPEN_MIN + p.range_min]
        if len(rng) < p.range_min // 3:   # thin/holiday open: skip the day
            continue
        hi, lo = float(rng["high"].max()), float(rng["low"].min())
        if hi <= lo:
            continue

        # volatility-regime gate (round 2): the day's opening range vs its own
        # trailing history. Percentile uses ONLY prior days (causal); today's
        # range is appended AFTER the decision.
        or_bps = (hi - lo) / ((hi + lo) / 2) * 1e4
        if p.vol_pct > 0.0:
            if len(recent_ranges) < VOL_LOOKBACK:
                recent_ranges.append(or_bps)
                continue  # warmup: no trade until a trailing window exists
            threshold = float(np.quantile(recent_ranges[-VOL_LOOKBACK:], p.vol_pct))
            hot = or_bps >= threshold
            recent_ranges.append(or_bps)
            if not hot:
                continue
        else:
            recent_ranges.append(or_bps)

        window = d[(d["minute"] >= OPEN_MIN + p.range_min) & (d["minute"] < DAY_END)]
        if window.empty:
            continue
        closes = window["close"].to_numpy()
        highs = window["high"].to_numpy()
        lows = window["low"].to_numpy()
        minutes = window["minute"].to_numpy()
        times = window["time"].reset_index(drop=True)

        entry_i, direction = None, 0
        for i in range(len(window)):
            if minutes[i] >= ENTRY_CUTOFF:
                break
            if closes[i] > hi:
                entry_i, direction = i, 1
                break
            if closes[i] < lo:
                entry_i, direction = i, -1
                break
        if entry_i is None:
            continue

        entry = closes[entry_i]
        stop = lo if direction == 1 else hi
        risk = abs(entry - stop)
        if risk <= 0:
            continue
        target = entry + direction * p.target_r * risk if p.target_r > 0 else None

        exit_px, exit_i = None, len(window) - 1
        for j in range(entry_i + 1, len(window)):
            if direction == 1:
                if lows[j] <= stop:
                    exit_px, exit_i = stop, j
                    break
                if target is not None and highs[j] >= target:
                    exit_px, exit_i = target, j
                    break
            else:
                if highs[j] >= stop:
                    exit_px, exit_i = stop, j
                    break
                if target is not None and lows[j] <= target:
                    exit_px, exit_i = target, j
                    break
        if exit_px is None:
            exit_px = closes[-1]          # hard EOD exit at 15:55 NY
        gross_bps = direction * (exit_px - entry) / entry * 1e4
        trades.append(ORBTrade(times.iloc[entry_i], times.iloc[exit_i],
                               direction, gross_bps - COST_RT_BPS))
    return trades


@dataclass
class ORBWindow:
    symbol: str
    test_start: object
    params: dict
    train_net: float
    test_net: float
    test_trades: int


def walk_forward_orb(m1: pd.DataFrame, symbol: str, grid: dict | None = None
                     ) -> tuple[list[ORBWindow], list[ORBTrade]]:
    grid = grid or GRID
    m1 = prep(m1.sort_values("time", ignore_index=True))
    days = sorted(m1["day"].unique())
    windows: list[ORBWindow] = []
    oos: list[ORBTrade] = []
    start = 0
    while start + TRAIN_N + TEST_N <= len(days):
        train_days = set(days[start : start + TRAIN_N])
        test_days = set(days[start + TRAIN_N : start + TRAIN_N + TEST_N])
        train = m1[m1["day"].isin(train_days)]
        test = m1[m1["day"].isin(test_days)]

        best, best_net = None, float("-inf")
        for combo in product(*grid.values()):
            p = ORBParams(**dict(zip(grid, combo)))
            net = sum(t.net_bps for t in run_orb(train, p))
            if net > best_net:
                best_net, best = net, combo
        p = ORBParams(**dict(zip(grid, best)))
        trades = run_orb(test, p)
        windows.append(
            ORBWindow(symbol, days[start + TRAIN_N], dict(zip(GRID, best)),
                      best_net, sum(t.net_bps for t in trades), len(trades))
        )
        oos.extend(trades)
        start += ROLL_N
    return windows, oos
