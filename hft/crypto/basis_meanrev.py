"""C5 — perp_spot_basis_meanrev, implemented BLIND to any recorded data.

This module implements exactly the spec frozen in
reports/m3_preregistration.md before meaningful data existed. Implementation
constants not fixed there are fixed here, also blind, and may not be tuned
against data later without voiding the round:

- MATCH_TOLERANCE_MS = 500 (per pre-reg: snapshots matched within 500ms)
- DECISION_CADENCE_S = 5   (basis sampled to a regular 5s grid; signal and
  state machine evaluate on that grid)
- MIN_PERIODS: half the rolling window (z undefined before that)

Accounting per trade (unit notional, matching the pre-registered cost
model): gross = basis_mid(entry) - basis_mid(exit); costs = FEE_RT (25bp,
4 taker legs) + the four MEASURED half-spreads (perp+spot at entry,
perp+spot at exit). Only the z >= +z_enter side trades (short perp / long
spot); the negative side is recorded as a SHADOW trade list, non-gating.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

MATCH_TOLERANCE_MS = 500
DECISION_CADENCE_S = 5
FEE_RT = 25e-4  # 25bp round trip, 4 taker legs — pre-registered

GRID = {
    "w_min": [30, 120, 480],
    "z_enter": [1.5, 2.0, 3.0],
    "z_exit": [0.0, 0.5],
    "max_hold_min": [60, 240],
}
TRAIN_DAYS, TEST_DAYS, ROLL_DAYS = 10, 5, 5


@dataclass(frozen=True)
class C5Params:
    w_min: int = 120
    z_enter: float = 2.0
    z_exit: float = 0.0
    max_hold_min: int = 240


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    gross: float
    net: float
    shadow: bool  # True = untradeable negative-z side, non-gating


def load_books5(root: Path, inst: str) -> pd.DataFrame:
    files = sorted((Path(root) / inst / "books5").glob("*.parquet"))
    if not files:
        return pd.DataFrame(columns=["ts", "bid1_px", "ask1_px"])
    df = pd.concat(
        [pd.read_parquet(f, columns=["ts", "bid1_px", "ask1_px"]) for f in files],
        ignore_index=True,
    )
    df = df[(df["bid1_px"] > 0) & (df["ask1_px"] > 0)]
    return df.drop_duplicates("ts").sort_values("ts", ignore_index=True)


def build_basis_frame(perp: pd.DataFrame, spot: pd.DataFrame) -> pd.DataFrame:
    """Match perp/spot snapshots within tolerance, sample to the decision
    grid. Columns: basis (mid/mid - 1), hs_perp, hs_spot (half-spread
    fractions). Values at grid time t use the latest snapshot <= t."""
    merged = pd.merge_asof(
        perp.rename(columns={"bid1_px": "pb", "ask1_px": "pa"}),
        spot.rename(columns={"bid1_px": "sb", "ask1_px": "sa"}),
        on="ts",
        tolerance=MATCH_TOLERANCE_MS,
        direction="nearest",
    ).dropna()
    pm, sm = (merged["pb"] + merged["pa"]) / 2, (merged["sb"] + merged["sa"]) / 2
    # .to_numpy(): a fresh index is being attached, so the Series' own index
    # must not participate (pandas would align on labels and produce NaN)
    out = pd.DataFrame(
        {
            "basis": (pm / sm - 1).to_numpy(),
            "hs_perp": ((merged["pa"] - merged["pb"]) / 2 / pm).to_numpy(),
            "hs_spot": ((merged["sa"] - merged["sb"]) / 2 / sm).to_numpy(),
        },
        index=pd.to_datetime(merged["ts"], unit="ms", utc=True),
    )
    return out.resample(f"{DECISION_CADENCE_S}s").last().dropna()


def zscore(basis: pd.Series, w_min: int) -> pd.Series:
    """Causal: z at t uses samples strictly before t (shift by one)."""
    w = w_min * 60 // DECISION_CADENCE_S
    mean = basis.rolling(w, min_periods=w // 2).mean().shift(1)
    std = basis.rolling(w, min_periods=w // 2).std().shift(1)
    return (basis - mean) / std


def run_c5(frame: pd.DataFrame, p: C5Params) -> list[Trade]:
    z = zscore(frame["basis"], p.w_min).to_numpy()
    basis = frame["basis"].to_numpy()
    hs_total = (frame["hs_perp"] + frame["hs_spot"]).to_numpy()
    times = frame.index
    max_hold = p.max_hold_min * 60 // DECISION_CADENCE_S

    trades: list[Trade] = []
    state = 0  # 0 flat, +1 real (short perp/long spot), -1 shadow
    entry_i = 0
    for i in range(len(z)):
        if np.isnan(z[i]):
            continue
        if state == 0:
            if z[i] >= p.z_enter:
                state, entry_i = 1, i
            elif z[i] <= -p.z_enter:
                state, entry_i = -1, i
        else:
            reverted = (z[i] <= p.z_exit) if state == 1 else (z[i] >= -p.z_exit)
            if reverted or (i - entry_i) >= max_hold or i == len(z) - 1:
                sign = float(state)
                gross = sign * (basis[entry_i] - basis[i])
                net = gross - FEE_RT - hs_total[entry_i] - hs_total[i]
                trades.append(
                    Trade(times[entry_i], times[i], gross, net, shadow=(state == -1))
                )
                state = 0
    return trades


@dataclass
class C5Window:
    test_start: object
    params: dict
    train_net: float
    test_net: float
    test_trades: int


@dataclass
class C5RoundResult:
    windows: list[C5Window]
    oos_trades: list[Trade]  # real side only

    def gate(self) -> dict:
        nets = np.array([t.net for t in self.oos_trades])
        n = len(nets)
        mean = float(nets.mean()) if n else 0.0
        t = float(mean / (nets.std(ddof=1) / np.sqrt(n))) if n > 1 and nets.std(ddof=1) > 0 else 0.0
        stability = (
            sum(1 for w in self.windows if w.test_trades > 0 and w.test_net > 0)
            / len(self.windows)
            if self.windows
            else 0.0
        )
        passed = n >= 100 and mean > 0 and t >= 2.0 and stability >= 0.6
        return {"trades": n, "mean_net": mean, "t": t, "stability": stability, "passed": passed}


def _grid_points() -> list[dict]:
    keys = list(GRID)
    return [dict(zip(keys, v)) for v in product(*(GRID[k] for k in keys))]


def walk_forward_c5(frame: pd.DataFrame) -> C5RoundResult:
    """Pre-registered scheme: train 10 recorded days / test 5, rolled by 5;
    optimize by total after-cost net on train (real side), freeze, evaluate."""
    days = sorted(set(frame.index.date))
    windows: list[C5Window] = []
    oos: list[Trade] = []
    start = 0
    while start + TRAIN_DAYS + TEST_DAYS <= len(days):
        train_days = set(days[start : start + TRAIN_DAYS])
        test_days = set(days[start + TRAIN_DAYS : start + TRAIN_DAYS + TEST_DAYS])
        train = frame[[d in train_days for d in frame.index.date]]
        test = frame[[d in test_days for d in frame.index.date]]

        best, best_net = None, float("-inf")
        for g in _grid_points():
            p = C5Params(**g)
            net = sum(t.net for t in run_c5(train, p) if not t.shadow)
            if net > best_net:
                best_net, best = net, g

        trades = [t for t in run_c5(test, C5Params(**best)) if not t.shadow]
        windows.append(
            C5Window(
                test_start=min(test_days),
                params=best,
                train_net=best_net,
                test_net=sum(t.net for t in trades),
                test_trades=len(trades),
            )
        )
        oos.extend(trades)
        start += ROLL_DAYS
    return C5RoundResult(windows, oos)
