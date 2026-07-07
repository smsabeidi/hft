"""C7 — fx_carry_vol_filtered, implemented exactly per the frozen spec in
reports/c7_preregistration.md.

Signal at day t uses information through t-1 only: the rate differential is
shifted one day (and monthly legs forward-fill, an inherently stale/lagged
publication), the vol filter compares yesterday's trailing 20d realized vol
to yesterday's trailing 1y quantile. Positions change at the daily close;
changes pay the conservative repo cost model (spread 0.7 + slippage 0.2 per
market fill + commission 0.7 pips RT). While in position, daily swap accrual
= (pos x differential - markup) / 252, with the markup m charged in BOTH
directions (retail brokers mark up both sides).

An EPISODE is a contiguous run of nonzero position in an OOS test window
(window edges truncate episodes; a sign flip ends one and starts another).
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

PIP = 0.0001
COST_RT_PIPS = 0.7 + 2 * 0.2 + 0.7  # spread + slippage both fills + commission
TRADING_DAYS = 252

GRID = {"thresh_bps": [0.0, 50.0, 100.0], "vol_q": [None, 0.80]}
TRAIN_N, TEST_N, ROLL_N = 500, 120, 120

RATE_FILES = {"USD": "USD_DTB3", "EUR": "EUR_ECBDFR",
              "GBP": "GBP_IR3TIB01GBM156N", "AUD": "AUD_IR3TIB01AUM156N"}
PAIRS = {"EURUSD": "EUR", "GBPUSD": "GBP", "AUDUSD": "AUD"}


@dataclass(frozen=True)
class CarryParams:
    thresh_bps: float = 0.0
    vol_q: float | None = None
    markup_pct: float = 1.0  # %/yr, both directions — gate scenario 1.0


@dataclass
class CarryEpisode:
    start: object
    end: object
    days: int
    net_return: float


def daily_bars_from_m1(m1: pd.DataFrame) -> pd.DataFrame:
    """Daily closes with the 22:00 UTC boundary (bar at 22:00 belongs to the
    NEXT trading day, matching broker/rollover convention)."""
    t = m1["time"] + pd.Timedelta(hours=2)
    df = pd.DataFrame({"day": t.dt.date, "close": m1["close"]})
    out = df.groupby("day", as_index=False).last()
    out["day"] = pd.to_datetime(out["day"])
    return out


def load_rates(rates_dir: Path) -> pd.DataFrame:
    """Daily forward-filled rate panel (%/yr) for USD/EUR/GBP/AUD."""
    cols = {}
    for ccy, stem in RATE_FILES.items():
        df = pd.read_parquet(rates_dir / f"{stem}.parquet")
        cols[ccy] = df.set_index("date")["rate"]
    panel = pd.DataFrame(cols).sort_index()
    idx = pd.date_range(panel.index.min(), pd.Timestamp.now().normalize(), freq="D")
    return panel.reindex(idx).ffill()


def build_pair_frame(bars: pd.DataFrame, rates: pd.DataFrame, base_ccy: str) -> pd.DataFrame:
    """Columns: close, ret, diff_pct (CAUSAL: shifted), vol20 (causal)."""
    df = bars.set_index("day").copy()
    diff = (rates[base_ccy] - rates["USD"]).reindex(df.index).ffill()
    df["diff_pct"] = diff.shift(1)
    df["ret"] = df["close"].pct_change()
    vol = df["ret"].rolling(20).std() * np.sqrt(TRADING_DAYS)
    df["vol20"] = vol.shift(1)
    df["vol_q80"] = vol.rolling(TRADING_DAYS).quantile(0.80).shift(1)
    return df.dropna(subset=["ret"])


def positions(frame: pd.DataFrame, p: CarryParams) -> np.ndarray:
    diff = frame["diff_pct"].to_numpy()
    thresh = p.thresh_bps / 100.0  # bps annualized -> percent
    pos = np.where(diff > thresh, 1.0, np.where(diff < -thresh, -1.0, 0.0))
    pos[np.isnan(diff)] = 0.0
    if p.vol_q is not None:
        hot = frame["vol20"].to_numpy() > frame["vol_q80"].to_numpy()
        pos = np.where(hot | np.isnan(frame["vol_q80"].to_numpy()), 0.0, pos)
    return pos


def daily_pnl(frame: pd.DataFrame, p: CarryParams) -> tuple[np.ndarray, np.ndarray]:
    """Per-day return contributions and the position vector."""
    pos = positions(frame, p)
    ret = frame["ret"].to_numpy()
    diff = np.nan_to_num(frame["diff_pct"].to_numpy())
    price = frame["close"].to_numpy()

    price_pnl = pos * ret
    carry = np.where(pos != 0.0, (pos * diff - p.markup_pct) / 100.0 / TRADING_DAYS, 0.0)
    turnover = np.abs(np.diff(pos, prepend=0.0))
    costs = turnover * (COST_RT_PIPS / 2) * PIP / price
    return price_pnl + carry - costs, pos


def episodes_from(frame: pd.DataFrame, pnl: np.ndarray, pos: np.ndarray) -> list[CarryEpisode]:
    out: list[CarryEpisode] = []
    idx = frame.index
    start = None
    acc = 0.0
    for i in range(len(pos)):
        active = pos[i] != 0.0
        flipped = active and start is not None and pos[i] != pos[i - 1] and pos[i - 1] != 0.0
        if (not active or flipped) and start is not None:
            out.append(CarryEpisode(idx[start], idx[i - 1], i - start, acc))
            start, acc = None, 0.0
        if active and start is None:
            start = i
        if active:
            acc += pnl[i]
    if start is not None:
        out.append(CarryEpisode(idx[start], idx[-1], len(pos) - start, acc))
    return out


@dataclass
class CarryWindow:
    pair: str
    test_start: object
    params: dict
    train_net: float
    test_net: float
    test_episodes: int


def walk_forward_carry(
    frame: pd.DataFrame, pair: str, markup_pct: float
) -> tuple[list[CarryWindow], list[CarryEpisode]]:
    windows: list[CarryWindow] = []
    oos: list[CarryEpisode] = []
    start = 0
    n = len(frame)
    while start + TRAIN_N + TEST_N <= n:
        train = frame.iloc[start : start + TRAIN_N]
        test = frame.iloc[start + TRAIN_N : start + TRAIN_N + TEST_N]

        best, best_net = None, float("-inf")
        for combo in product(*GRID.values()):
            p = CarryParams(*combo, markup_pct=markup_pct)
            net = float(daily_pnl(train, p)[0].sum())
            if net > best_net:
                best_net, best = net, combo
        p = CarryParams(*best, markup_pct=markup_pct)
        pnl, pos = daily_pnl(test, p)
        eps = episodes_from(test, pnl, pos)
        windows.append(
            CarryWindow(pair, test.index[0].date(), dict(zip(GRID, best)),
                        best_net, float(pnl.sum()), len(eps))
        )
        oos.extend(eps)
        start += ROLL_N
    return windows, oos
