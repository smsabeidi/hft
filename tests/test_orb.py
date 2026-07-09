"""us_open_orb_indices machinery — synthetic tests before the round."""

from __future__ import annotations

import pandas as pd
import pytest

from hft.strategies.orb import COST_RT_BPS, ORBParams, prep, run_orb


def _day(date_str: str, bars: list[tuple[str, float, float, float, float]]):
    """bars: (NY 'HH:MM', o, h, l, c) -> UTC-tz rows."""
    rows = []
    for hhmm, o, h, lo, c in bars:
        t = pd.Timestamp(f"{date_str} {hhmm}", tz="America/New_York").tz_convert("UTC")
        rows.append({"time": t, "open": o, "high": h, "low": lo, "close": c})
    return rows


def _flat_minutes(date_str, start_hhmm, n, px):
    out = []
    t0 = pd.Timestamp(f"{date_str} {start_hhmm}", tz="America/New_York")
    for k in range(n):
        t = (t0 + pd.Timedelta(minutes=k)).tz_convert("UTC")
        out.append({"time": t, "open": px, "high": px, "low": px, "close": px})
    return out


def test_long_breakout_stop_and_eod():
    base = 5000.0
    rows = []
    # opening range 09:30-10:00 between 4990 and 5010
    rows += _flat_minutes("2024-03-04", "09:30", 15, base - 10)
    rows += _flat_minutes("2024-03-04", "09:45", 15, base + 10)
    # breakout close above 5010 at 10:05
    rows += _day("2024-03-04", [("10:05", base + 10, base + 16, base + 10, base + 15)])
    # drift, then EOD
    rows += _flat_minutes("2024-03-04", "10:06", 5, base + 20)
    rows += _day("2024-03-04", [("15:54", base + 30, base + 30, base + 30, base + 30)])
    m1 = prep(pd.DataFrame(rows))
    trades = run_orb(m1, ORBParams(range_min=30, target_r=0.0))
    assert len(trades) == 1
    tr = trades[0]
    assert tr.direction == 1
    expected = (base + 30 - (base + 15)) / (base + 15) * 1e4 - COST_RT_BPS
    assert tr.net_bps == pytest.approx(expected, abs=0.01)


def test_stop_at_opposite_range_edge():
    base = 5000.0
    rows = []
    rows += _flat_minutes("2024-03-04", "09:30", 15, base - 10)
    rows += _flat_minutes("2024-03-04", "09:45", 15, base + 10)
    rows += _day("2024-03-04", [("10:05", base + 10, base + 16, base + 10, base + 15)])
    # collapse through the range low (stop = 4990)
    rows += _day("2024-03-04", [("10:30", base, base, base - 30, base - 20)])
    m1 = prep(pd.DataFrame(rows))
    trades = run_orb(m1, ORBParams(range_min=30, target_r=0.0))
    assert len(trades) == 1
    expected = ((base - 10) - (base + 15)) / (base + 15) * 1e4 - COST_RT_BPS
    assert trades[0].net_bps == pytest.approx(expected, abs=0.01)


def test_no_entry_after_noon_cutoff():
    base = 5000.0
    rows = []
    rows += _flat_minutes("2024-03-04", "09:30", 30, base)
    rows += _day("2024-03-04", [("12:01", base, base + 30, base, base + 25)])  # too late
    m1 = prep(pd.DataFrame(rows))
    assert run_orb(m1, ORBParams(range_min=30)) == []


def test_dst_independence_ny_clock():
    """Same NY-clock day in winter and summer must both produce the trade,
    though their UTC offsets differ (EST vs EDT)."""
    for date_str in ("2024-01-08", "2024-07-08"):
        base = 5000.0
        rows = []
        rows += _flat_minutes(date_str, "09:30", 15, base - 5)   # range needs width
        rows += _flat_minutes(date_str, "09:45", 15, base + 5)
        rows += _day(date_str, [("10:05", base + 5, base + 9, base + 5, base + 8)])
        rows += _day(date_str, [("15:54", base + 10, base + 10, base + 10, base + 10)])
        m1 = prep(pd.DataFrame(rows))
        trades = run_orb(m1, ORBParams(range_min=30, target_r=0.0))
        assert len(trades) == 1, f"missed trade on {date_str}"
