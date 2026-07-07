"""fvg_retest — the ICT/SMC menu's crispest representative, pre-registered.

FOUNDER SCOPE NOTE (2026-07-07): the standing "no further ad-hoc forex
families" rule is amended by explicit founder direction naming this class
(FVG / supply-demand / S-R retest / retracement). FVG retest is tested as
the class representative (first-named). Each further named pattern is its
own family, costing its own founder sign-off and 2 rounds.

Definition (frozen before any run):
- M5 bars aggregated from M1. Bullish FVG at bar i: low[i] > high[i-2]
  (3-bar imbalance; bar i-1 is the impulse). Zone = [high[i-2], low[i]],
  size >= min_gap_pips. Bearish mirrored.
- Entry: limit at the zone MIDPOINT, armed after bar i closes, live for
  max_wait M5 bars; filled when price trades through the midpoint.
- Stop: far edge of the zone. Target: rr x (entry - stop). The founder's
  requested geometry: rr in {3, 4}.
- Bracket resolution on M1 bars, STOP PRIORITY within a bar (conservative).
  One position at a time per pair; new signals ignored while in a trade.
- Costs: 1.05 pips RT flat (0.25 spread + 0.7 commission + 0.1 slippage —
  the FRIENDLY end, so a FAIL is conclusive; limit entries in reality still
  pay commission and exit spread).

PRE-REGISTERED GATE (identical shape to forex round 1):
- walk-forward train 500 / test 120 calendar days rolled by 120, grid
  optimized on train by after-cost net: min_gap_pips in {2, 5},
  max_wait in {12, 48} bars, rr in {3, 4}.
- pooled EURUSD+GBPUSD+AUDUSD OOS: >= 100 trades, mean net > 0 pips,
  t >= 2.0, window stability >= 0.6. Two failed rounds kill the family.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import numpy as np
import pandas as pd

PIP = 0.0001
COST_RT_PIPS = 1.05
GRID = {"min_gap_pips": [2.0, 5.0], "max_wait": [12, 48], "rr": [3.0, 4.0]}
TRAIN_DAYS, TEST_DAYS = 500, 120


@dataclass(frozen=True)
class FVGParams:
    min_gap_pips: float = 2.0
    max_wait: int = 12
    rr: float = 3.0


@dataclass
class FVGTrade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    direction: int
    net_pips: float


def m5_from_m1(m1: pd.DataFrame) -> pd.DataFrame:
    df = m1.set_index("time")
    m5 = df.resample("5min").agg(
        open=("open", "first"), high=("high", "max"),
        low=("low", "min"), close=("close", "last"),
    ).dropna()
    return m5.reset_index()


def find_fvgs(m5: pd.DataFrame, min_gap_pips: float) -> list[dict]:
    """3-bar imbalances, detected at the close of bar i (causal)."""
    h = m5["high"].to_numpy()
    lo = m5["low"].to_numpy()
    t = m5["time"]
    out = []
    gap_min = min_gap_pips * PIP
    for i in range(2, len(m5)):
        if lo[i] - h[i - 2] >= gap_min:      # bullish gap below price
            out.append({"i": i, "dir": 1, "top": lo[i], "bottom": h[i - 2], "time": t.iloc[i]})
        elif lo[i - 2] - h[i] >= gap_min:    # bearish gap above price
            out.append({"i": i, "dir": -1, "top": lo[i - 2], "bottom": h[i], "time": t.iloc[i]})
    return out


def run_fvg(m1: pd.DataFrame, m5: pd.DataFrame, p: FVGParams) -> list[FVGTrade]:
    """Arm limits at zone midpoints after formation; resolve entries on M5
    touches, then brackets on M1 bars with stop priority."""
    fvgs = find_fvgs(m5, p.min_gap_pips)
    m5h, m5l = m5["high"].to_numpy(), m5["low"].to_numpy()
    m5t = m5["time"]
    m1t = m1["time"].astype("int64").to_numpy()  # ns since epoch: tz-proof
    m1h, m1l = m1["high"].to_numpy(), m1["low"].to_numpy()

    trades: list[FVGTrade] = []
    busy_until = m5t.iloc[0] - pd.Timedelta(minutes=1)

    for f in fvgs:
        if f["time"] <= busy_until:
            continue
        mid = (f["top"] + f["bottom"]) / 2
        stop = f["bottom"] if f["dir"] == 1 else f["top"]
        risk = abs(mid - stop)
        if risk <= 0:
            continue
        target = mid + f["dir"] * p.rr * risk

        # entry: first M5 bar after formation that trades through the midpoint
        entry_j = None
        for j in range(f["i"] + 1, min(f["i"] + 1 + p.max_wait, len(m5))):
            touched = (m5l[j] <= mid) if f["dir"] == 1 else (m5h[j] >= mid)
            if touched:
                entry_j = j
                break
        if entry_j is None:
            continue
        entry_time = m5t.iloc[entry_j]

        # bracket on M1 bars from the entry bar onward, stop priority
        k0 = np.searchsorted(m1t, entry_time.value)
        exit_time, net = None, None
        for k in range(k0, len(m1t)):
            if f["dir"] == 1:
                if m1l[k] <= stop:
                    exit_time, net = m1t[k], -(risk / PIP)
                    break
                if m1h[k] >= target:
                    exit_time, net = m1t[k], p.rr * risk / PIP
                    break
            else:
                if m1h[k] >= stop:
                    exit_time, net = m1t[k], -(risk / PIP)
                    break
                if m1l[k] <= target:
                    exit_time, net = m1t[k], p.rr * risk / PIP
                    break
        if exit_time is None:
            continue  # never resolved before data end: drop, do not guess
        exit_ts = pd.Timestamp(exit_time, tz="UTC")
        trades.append(FVGTrade(entry_time, exit_ts, f["dir"], net - COST_RT_PIPS))
        busy_until = exit_ts
    return trades


@dataclass
class FVGWindow:
    pair: str
    test_start: object
    params: dict
    train_net: float
    test_net: float
    test_trades: int


def walk_forward_fvg(m1: pd.DataFrame, pair: str) -> tuple[list[FVGWindow], list[FVGTrade]]:
    m1 = m1.sort_values("time", ignore_index=True)
    m5 = m5_from_m1(m1)
    days = m1["time"].dt.normalize()
    d0, d1 = days.iloc[0], days.iloc[-1]

    windows: list[FVGWindow] = []
    oos: list[FVGTrade] = []
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
            p = FVGParams(*combo)
            net = sum(t.net_pips for t in run_fvg(m1_tr, m5_tr, p))
            if net > best_net:
                best_net, best = net, combo
        p = FVGParams(*best)
        trades = run_fvg(m1_te, m5_te, p)
        windows.append(
            FVGWindow(pair, t_end.date(), dict(zip(GRID, best)), best_net,
                      sum(t.net_pips for t in trades), len(trades))
        )
        oos.extend(trades)
        start += pd.Timedelta(days=TEST_DAYS)
    return windows, oos
