"""C7 carry machinery — synthetic tests (spec: reports/c7_preregistration.md)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hft.strategies.carry import (
    CarryParams,
    daily_bars_from_m1,
    daily_pnl,
    episodes_from,
    positions,
)


def _frame(n=300, diff_pct=2.0, price=1.10, vol=0.0, seed=1):
    rng = np.random.default_rng(seed)
    ret = rng.normal(0, vol, n)
    close = price * np.cumprod(1 + ret)
    idx = pd.date_range("2023-01-02", periods=n, freq="B")
    df = pd.DataFrame({"close": close, "ret": ret, "diff_pct": diff_pct}, index=idx)
    realized = pd.Series(ret, index=idx).rolling(20).std() * np.sqrt(252)
    df["vol20"] = realized.shift(1)
    df["vol_q80"] = realized.rolling(252).quantile(0.8).shift(1)
    return df


def test_daily_bars_2200_boundary():
    t = pd.to_datetime(["2024-01-02 21:59", "2024-01-02 22:00"], utc=True)
    m1 = pd.DataFrame({"time": t, "close": [1.0, 2.0]})
    bars = daily_bars_from_m1(m1)
    # 22:00 belongs to the NEXT day: two distinct daily bars
    assert len(bars) == 2
    assert bars["close"].tolist() == [1.0, 2.0]


def test_position_follows_differential_sign_and_threshold():
    f = _frame(diff_pct=0.8)
    assert (positions(f, CarryParams(thresh_bps=0.0)) == 1.0).all()
    assert (positions(f, CarryParams(thresh_bps=100.0)) == 0.0).all()  # 0.8% < 1%
    f_neg = _frame(diff_pct=-2.0)
    assert (positions(f_neg, CarryParams(thresh_bps=50.0)) == -1.0).all()


def test_carry_accrual_and_markup():
    f = _frame(n=252, diff_pct=2.0, vol=0.0)
    pnl_m0, _ = daily_pnl(f, CarryParams(markup_pct=0.0))
    pnl_m1, _ = daily_pnl(f, CarryParams(markup_pct=1.0))
    # flat prices: pnl is pure carry minus one entry cost; ~2%/yr vs ~1%/yr
    assert pnl_m0.sum() == pytest.approx(0.02, abs=0.002)
    assert pnl_m1.sum() == pytest.approx(0.01, abs=0.002)


def test_markup_charged_on_short_side_too():
    f = _frame(n=252, diff_pct=-2.0, vol=0.0)
    pnl, pos = daily_pnl(f, CarryParams(markup_pct=1.0))
    assert (pos == -1.0).all()
    assert pnl.sum() == pytest.approx(0.01, abs=0.002)  # |diff| - markup


def test_vol_filter_flattens_hot_regime():
    f = _frame(n=600, diff_pct=2.0, vol=0.002, seed=2)
    f.loc[f.index[400:440], "vol20"] = 1.0  # force hot regime
    pos = positions(f, CarryParams(vol_q=0.80))
    assert (pos[400:440] == 0.0).all()


def test_episode_segmentation_counts_flips_and_gaps():
    f = _frame(n=10, diff_pct=2.0, vol=0.0)
    pos = np.array([0, 1, 1, 0, 1, 1, -1, -1, 0, 0], dtype=float)
    pnl = np.ones(10) * 0.001
    eps = episodes_from(f, pnl, pos)
    assert len(eps) == 3            # run, run, flipped run
    assert eps[0].days == 2 and eps[2].days == 2


def test_signal_is_causal_columns_shifted():
    """diff_pct/vol20 must already be shifted by the loader; here we assert
    the pnl at day t doesn't depend on ret at day t via the signal path:
    changing today's return must not change today's position."""
    f = _frame(n=100, diff_pct=2.0, vol=0.001, seed=3)
    pos_a = positions(f, CarryParams(vol_q=0.80))
    f2 = f.copy()
    f2.iloc[-1, f2.columns.get_loc("ret")] = 0.05  # shock today's return only
    pos_b = positions(f2, CarryParams(vol_q=0.80))
    assert (pos_a == pos_b).all()
