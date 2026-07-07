"""fvg_rel (round 2, relative units) — synthetic tests before the run."""

from __future__ import annotations

import pandas as pd
import pytest

from hft.strategies.fvg_rel import FVGRelParams, find_fvgs_rel, run_fvg_rel


def _m5(rows, start="2024-01-02 00:00"):
    t = pd.date_range(start, periods=len(rows), freq="5min", tz="UTC")
    o, h, lo, c = zip(*rows)
    return pd.DataFrame({"time": t, "open": o, "high": h, "low": lo, "close": c})


def _m1_from_m5(m5):
    rows = []
    for _, r in m5.iterrows():
        for k in range(5):
            rows.append({"time": r["time"] + pd.Timedelta(minutes=k),
                         "open": r["open"], "high": r["high"],
                         "low": r["low"], "close": r["close"]})
    return pd.DataFrame(rows)


def test_gap_floor_is_relative_to_price():
    # identical 4bp gap at two very different price levels must both qualify
    for base in (2_400.0, 100_000.0):
        gap = 4e-4 * base
        rows = [(base, base + gap / 4, base - gap / 4, base),
                (base, base + 3 * gap, base, base + 3 * gap),
                (base + 3 * gap, base + 3.2 * gap, base + gap / 4 + gap, base + 3 * gap)]
        fvgs = find_fvgs_rel(_m5(rows), min_gap_bps=2.0)
        assert len(fvgs) == 1, f"gap missed at price {base}"
        assert find_fvgs_rel(_m5(rows), min_gap_bps=5.0) == []


def test_gross_is_rr_multiple_of_risk_bps():
    base = 100_000.0
    zone_bottom, zone_top = base + 2.0, base + 42.0  # 40 units = 4bp zone
    rows = [(base, zone_bottom, base - 40.0, base),
            (base, base + 300.0, base, base + 300.0),
            (base + 300.0, base + 320.0, zone_top, base + 300.0),
            # retest through midpoint then rally through 3R target
            (base + 300.0, base + 300.0, zone_bottom + 15.0, base + 100.0),
            (base + 100.0, base + 900.0, base + 100.0, base + 900.0)]
    m5 = _m5(rows)
    trades = run_fvg_rel(_m1_from_m5(m5), m5, FVGRelParams(min_gap_bps=2.0, max_wait=12, rr=3.0))
    assert len(trades) == 1
    tr = trades[0]
    mid = (zone_bottom + zone_top) / 2
    risk_bps = (mid - zone_bottom) / mid * 1e4
    assert tr.gross_bps == pytest.approx(3.0 * risk_bps, rel=1e-6)


def test_stop_priority_and_loss_size():
    base = 2_400.0
    zone_bottom, zone_top = base + 0.5, base + 1.5
    rows = [(base, zone_bottom, base - 1.0, base),
            (base, base + 8.0, base, base + 8.0),
            (base + 8.0, base + 8.5, zone_top, base + 8.0),
            (base + 8.0, base + 20.0, zone_bottom - 0.5, base + 5.0)]  # spans everything
    m5 = _m5(rows)
    trades = run_fvg_rel(_m1_from_m5(m5), m5, FVGRelParams(min_gap_bps=2.0, max_wait=12, rr=3.0))
    assert len(trades) == 1
    mid = (zone_bottom + zone_top) / 2
    assert trades[0].gross_bps == pytest.approx(-(mid - zone_bottom) / mid * 1e4, rel=1e-6)
