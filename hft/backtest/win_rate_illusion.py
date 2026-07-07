"""The win-rate illusion, made measurable.

Every "99% win rate" EA on the marketplace is one payoff geometry: a tiny
take-profit and a huge stop-loss. Win rate is a DIAL SET BY GEOMETRY, not
evidence of skill: with signal-free entries on a fair price series, the
probability a bracket exits at the target before the stop is roughly
sl/(tp+sl) — set tp=2, sl=100 and you win ~98% of the time while expectancy
stays exactly zero minus costs. This module simulates signal-free bracket
trades (alternating direction, fixed cadence — no forecast anywhere) on real
M1 bars so the geometry-vs-expectancy split is measured, not argued.

Accounting: mid-based entries at bar open with a lump round-trip cost in
pips (spread + commission + slippage; 0 for the frictionless panel). Within
a bar, STOP has priority over target (conservative, standard). One position
at a time; entries only while flat.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

PIP = 0.0001


@dataclass(frozen=True)
class BracketSpec:
    name: str
    tp_pips: float
    sl_pips: float


@dataclass
class BracketResult:
    name: str
    trades: int
    win_rate: float
    expectancy_pips: float
    t_stat: float
    total_pips: float
    max_dd_pips: float
    losses_to_erase: float  # wins one loss wipes out

    @classmethod
    def from_pnls(cls, name: str, pnls: np.ndarray, tp: float, sl: float) -> "BracketResult":
        n = len(pnls)
        wins = pnls > 0
        mean = float(pnls.mean()) if n else 0.0
        sd = float(pnls.std(ddof=1)) if n > 1 else 0.0
        equity = np.cumsum(pnls)
        peak = np.maximum.accumulate(np.concatenate([[0.0], equity]))
        dd = float((peak[1:] - equity).max()) if n else 0.0
        return cls(
            name=name,
            trades=n,
            win_rate=float(wins.mean()) if n else 0.0,
            expectancy_pips=mean,
            t_stat=mean / (sd / np.sqrt(n)) if n > 1 and sd > 0 else 0.0,
            total_pips=float(pnls.sum()),
            max_dd_pips=dd,
            losses_to_erase=sl / tp if tp > 0 else float("inf"),
        )


def simulate_bracket(
    bars: pd.DataFrame,
    spec: BracketSpec,
    cost_rt_pips: float,
    entry_every_min: int = 30,
    max_hold_bars: int = 7_200,
) -> np.ndarray:
    """Signal-free brackets: enter at bar open every entry_every_min minutes
    while flat, direction strictly alternating (long, short, long, ...).
    Returns per-trade P&L in pips."""
    o = bars["open"].to_numpy()
    h = bars["high"].to_numpy()
    lo = bars["low"].to_numpy()
    minutes = bars["time"].dt.minute.to_numpy()
    entry_ok = (minutes % entry_every_min) == 0

    tp, sl = spec.tp_pips * PIP, spec.sl_pips * PIP
    pnls: list[float] = []
    i, direction, n = 0, 1, len(o)
    while i < n:
        if not entry_ok[i]:
            i += 1
            continue
        entry = o[i]
        end = min(i + max_hold_bars, n - 1)
        pnl_pips = None
        j = i
        for j in range(i, end + 1):
            if direction > 0:
                if lo[j] <= entry - sl:          # stop first, always
                    pnl_pips = -spec.sl_pips
                    break
                if h[j] >= entry + tp:
                    pnl_pips = spec.tp_pips
                    break
            else:
                if h[j] >= entry + sl:
                    pnl_pips = -spec.sl_pips
                    break
                if lo[j] <= entry - tp:
                    pnl_pips = spec.tp_pips
                    break
        if pnl_pips is None:  # time-capped: exit at the cap bar's open
            pnl_pips = direction * (o[end] - entry) / PIP
            j = end
        pnls.append(pnl_pips - cost_rt_pips)
        direction = -direction
        i = j + 1
    return np.asarray(pnls)
