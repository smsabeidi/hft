"""fvg_retest machinery — synthetic tests, written before the round runs."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hft.strategies.fvg import COST_RT_PIPS, FVGParams, find_fvgs, m5_from_m1, run_fvg

PIP = 0.0001


def _m5(rows):
    """rows: (o, h, l, c) tuples at 5-minute spacing."""
    t = pd.date_range("2024-01-02 00:00", periods=len(rows), freq="5min", tz="UTC")
    o, h, lo, c = zip(*rows)
    return pd.DataFrame({"time": t, "open": o, "high": h, "low": lo, "close": c})


def _m1_from_m5(m5):
    """Flat M1 bars replicating each M5 bar (good enough for bracket tests)."""
    rows = []
    for _, r in m5.iterrows():
        for k in range(5):
            rows.append({"time": r["time"] + pd.Timedelta(minutes=k),
                         "open": r["open"], "high": r["high"],
                         "low": r["low"], "close": r["close"]})
    return pd.DataFrame(rows)


def test_bullish_fvg_detected_with_min_size():
    base = 1.1000
    rows = [(base, base + 2e-4, base - 2e-4, base),                # i-2 high = 1.1002
            (base, base + 30e-4, base, base + 30e-4),              # impulse
            (base + 30e-4, base + 32e-4, base + 6e-4, base + 30e-4)]  # low 1.1006 > 1.1002
    fvgs = find_fvgs(_m5(rows), min_gap_pips=2.0)
    assert len(fvgs) == 1
    f = fvgs[0]
    assert f["dir"] == 1
    assert f["bottom"] == pytest.approx(base + 2e-4)
    assert f["top"] == pytest.approx(base + 6e-4)
    assert find_fvgs(_m5(rows), min_gap_pips=5.0) == []  # 4 pips < 5 floor


def test_retest_entry_and_target_hit():
    base = 1.1000
    rows = [(base, base + 2e-4, base - 2e-4, base),
            (base, base + 30e-4, base, base + 30e-4),
            (base + 30e-4, base + 32e-4, base + 6e-4, base + 30e-4),
            # retest: trades down through the midpoint 1.1004
            (base + 30e-4, base + 30e-4, base + 3.5e-4, base + 10e-4),
            # then rallies through the 3R target
            (base + 10e-4, base + 40e-4, base + 10e-4, base + 40e-4)]
    m5 = _m5(rows)
    trades = run_fvg(_m1_from_m5(m5), m5, FVGParams(min_gap_pips=2.0, max_wait=12, rr=3.0))
    assert len(trades) == 1
    tr = trades[0]
    assert tr.direction == 1
    # mid 1.1004, stop 1.1002 -> risk 2 pips, win = 6 pips - costs
    assert tr.net_pips == pytest.approx(6.0 - COST_RT_PIPS, abs=1e-6)


def test_stop_priority_when_bar_spans_both():
    base = 1.1000
    rows = [(base, base + 2e-4, base - 2e-4, base),
            (base, base + 30e-4, base, base + 30e-4),
            (base + 30e-4, base + 32e-4, base + 6e-4, base + 30e-4),
            # one wide bar: touches mid, stop AND target -> stop must win
            (base + 30e-4, base + 40e-4, base + 1e-4, base + 20e-4)]
    m5 = _m5(rows)
    trades = run_fvg(_m1_from_m5(m5), m5, FVGParams(min_gap_pips=2.0, max_wait=12, rr=3.0))
    assert len(trades) == 1
    assert trades[0].net_pips == pytest.approx(-2.0 - COST_RT_PIPS, abs=1e-6)


def test_no_entry_when_never_retested():
    base = 1.1000
    rows = [(base, base + 2e-4, base - 2e-4, base),
            (base, base + 30e-4, base, base + 30e-4),
            (base + 30e-4, base + 32e-4, base + 6e-4, base + 30e-4)] + \
           [(base + 30e-4, base + 31e-4, base + 29e-4, base + 30e-4)] * 15
    m5 = _m5(rows)
    trades = run_fvg(_m1_from_m5(m5), m5, FVGParams(min_gap_pips=2.0, max_wait=12, rr=3.0))
    assert trades == []


def test_bearish_mirror():
    base = 1.1000
    rows = [(base, base + 2e-4, base - 2e-4, base),
            (base, base, base - 30e-4, base - 30e-4),
            (base - 30e-4, base - 6e-4, base - 32e-4, base - 30e-4),
            (base - 30e-4, base - 3.5e-4, base - 30e-4, base - 10e-4),
            (base - 10e-4, base - 10e-4, base - 40e-4, base - 40e-4)]
    m5 = _m5(rows)
    trades = run_fvg(_m1_from_m5(m5), m5, FVGParams(min_gap_pips=2.0, max_wait=12, rr=3.0))
    assert len(trades) == 1
    assert trades[0].direction == -1
    assert trades[0].net_pips > 0
