"""fvg_retest ROUND 2 (of 2) — gold + BTC, relative units. Family decided
by this round per the standing 2-round kill rule.

Rationale: round 1 found a REAL entry signal on FX (t=+2.70, 23,714 trades)
that was ~1/8th the size of retail costs. XAUUSD and BTCUSD are the ICT
folklore's flagship instruments and carry much larger ranges relative to
spread — the one honest reason to spend the family's last round.

Same frozen definition as round 1 (hft/strategies/fvg.py), re-expressed in
RELATIVE units so one implementation serves $2,400 gold and $100k BTC:
- gap floor and risk in bps of price; grid min_gap_bps in {2, 5} (FX round's
  2/5 pips = 1.8/4.6bp — same magnitudes), max_wait in {12, 48}, rr in {3, 4}.
- entry limit at zone midpoint, stop at far edge, bracket on M1 bars with
  STOP PRIORITY, one position at a time.
- PRE-REGISTERED COSTS (friendly floors, so FAIL is conclusive):
  XAUUSD 2.0bp RT (retail ~30-40c spread+comm on ~$2,400);
  BTCUSD 10.0bp RT (perp taker 2x5bp; the retail CFD is worse).
  Conservative panel (4bp / 15bp) reported NON-GATING.
- GATE: pooled XAU+BTC OOS >= 100 trades, mean net > 0 bps at the friendly
  costs, t >= 2.0, window stability >= 0.6. Walk-forward 500/120 days.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import numpy as np
import pandas as pd

from hft.strategies.fvg import m5_from_m1

GRID = {"min_gap_bps": [2.0, 5.0], "max_wait": [12, 48], "rr": [3.0, 4.0]}
TRAIN_DAYS, TEST_DAYS = 500, 120


@dataclass(frozen=True)
class FVGRelParams:
    min_gap_bps: float = 2.0
    max_wait: int = 12
    rr: float = 3.0


@dataclass
class FVGRelTrade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    direction: int
    gross_bps: float  # cost-independent; net = gross - cost_rt_bps


def find_fvgs_rel(m5: pd.DataFrame, min_gap_bps: float) -> list[dict]:
    h = m5["high"].to_numpy()
    lo = m5["low"].to_numpy()
    t = m5["time"]
    out = []
    for i in range(2, len(m5)):
        mid = (h[i - 2] + lo[i]) / 2
        if lo[i] - h[i - 2] >= min_gap_bps / 1e4 * mid:
            out.append({"i": i, "dir": 1, "top": lo[i], "bottom": h[i - 2], "time": t.iloc[i]})
            continue
        mid = (lo[i - 2] + h[i]) / 2
        if lo[i - 2] - h[i] >= min_gap_bps / 1e4 * mid:
            out.append({"i": i, "dir": -1, "top": lo[i - 2], "bottom": h[i], "time": t.iloc[i]})
    return out


def run_fvg_rel(m1: pd.DataFrame, m5: pd.DataFrame, p: FVGRelParams) -> list[FVGRelTrade]:
    fvgs = find_fvgs_rel(m5, p.min_gap_bps)
    m5h, m5l = m5["high"].to_numpy(), m5["low"].to_numpy()
    m5t = m5["time"]
    m1t = m1["time"].astype("int64").to_numpy()
    m1h, m1l = m1["high"].to_numpy(), m1["low"].to_numpy()

    trades: list[FVGRelTrade] = []
    busy_until = m5t.iloc[0] - pd.Timedelta(minutes=1)

    for f in fvgs:
        if f["time"] <= busy_until:
            continue
        mid = (f["top"] + f["bottom"]) / 2
        stop = f["bottom"] if f["dir"] == 1 else f["top"]
        risk_bps = abs(mid - stop) / mid * 1e4
        if risk_bps <= 0:
            continue
        target = mid + f["dir"] * p.rr * abs(mid - stop)

        entry_j = None
        for j in range(f["i"] + 1, min(f["i"] + 1 + p.max_wait, len(m5))):
            touched = (m5l[j] <= mid) if f["dir"] == 1 else (m5h[j] >= mid)
            if touched:
                entry_j = j
                break
        if entry_j is None:
            continue
        entry_time = m5t.iloc[entry_j]

        k0 = np.searchsorted(m1t, entry_time.value)
        exit_time, gross = None, None
        for k in range(k0, len(m1t)):
            if f["dir"] == 1:
                if m1l[k] <= stop:
                    exit_time, gross = m1t[k], -risk_bps
                    break
                if m1h[k] >= target:
                    exit_time, gross = m1t[k], p.rr * risk_bps
                    break
            else:
                if m1h[k] >= stop:
                    exit_time, gross = m1t[k], -risk_bps
                    break
                if m1l[k] <= target:
                    exit_time, gross = m1t[k], p.rr * risk_bps
                    break
        if exit_time is None:
            continue
        exit_ts = pd.Timestamp(exit_time, tz="UTC")
        trades.append(FVGRelTrade(entry_time, exit_ts, f["dir"], gross))
        busy_until = exit_ts
    return trades


@dataclass
class FVGRelWindow:
    pair: str
    test_start: object
    params: dict
    train_net: float
    test_net: float
    test_trades: int


def walk_forward_fvg_rel(
    m1: pd.DataFrame, pair: str, cost_rt_bps: float
) -> tuple[list[FVGRelWindow], list[FVGRelTrade]]:
    m1 = m1.sort_values("time", ignore_index=True)
    m5 = m5_from_m1(m1)
    days = m1["time"].dt.normalize()
    d0, d1 = days.iloc[0], days.iloc[-1]

    windows: list[FVGRelWindow] = []
    oos: list[FVGRelTrade] = []
    start = d0
    while start + pd.Timedelta(days=TRAIN_DAYS + TEST_DAYS) <= d1:
        t_end = start + pd.Timedelta(days=TRAIN_DAYS)
        s_end = t_end + pd.Timedelta(days=TEST_DAYS)
        m1_tr = m1[(days >= start) & (days < t_end)]
        m1_te = m1[(days >= t_end) & (days < s_end)]
        m5_tr = m5[(m5["time"] >= start) & (m5["time"] < t_end)]
        m5_te = m5[(m5["time"] >= t_end) & (m5["time"] < s_end)]

        best, best_net = None, float("-inf")
        for combo in product(*GRID.values()):
            p = FVGRelParams(*combo)
            net = sum(t.gross_bps - cost_rt_bps for t in run_fvg_rel(m1_tr, m5_tr, p))
            if net > best_net:
                best_net, best = net, combo
        p = FVGRelParams(*best)
        trades = run_fvg_rel(m1_te, m5_te, p)
        windows.append(
            FVGRelWindow(pair, t_end.date(), dict(zip(GRID, best)), best_net,
                         sum(t.gross_bps - cost_rt_bps for t in trades), len(trades))
        )
        oos.extend(trades)
        start += pd.Timedelta(days=TEST_DAYS)
    return windows, oos
