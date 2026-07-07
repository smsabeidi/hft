from __future__ import annotations

import numpy as np
import pandas as pd

from hft.data.sanity import validate_ticks


def _ticks(times, bids, asks):
    return pd.DataFrame(
        {
            "time": pd.to_datetime(times, utc=True),
            "bid": bids,
            "ask": asks,
            "bid_vol": 1.0,
            "ask_vol": 1.0,
        }
    )


def test_clean_data_passes():
    times = pd.date_range("2026-01-06 10:00", periods=100, freq="s", tz="UTC")
    t = _ticks(times, np.full(100, 1.1000), np.full(100, 1.10007))
    clean, report = validate_ticks(t)
    assert report.issues == 0
    assert report.dropped == 0
    assert len(clean) == 100


def test_bad_ticks_dropped_not_modified():
    times = pd.date_range("2026-01-06 10:00", periods=6, freq="s", tz="UTC")
    bids = [1.1000, np.nan, 1.1000, 1.1000, 1.1000, 1.1000]
    asks = [1.10007, 1.10007, 1.0995, 1.10007, 1.10200, 1.10007]
    # idx1: NaN bid; idx2: crossed (ask<bid); idx4: spread outlier (19.3 pips vs 0.7 median)
    t = _ticks(times, bids, asks)
    clean, report = validate_ticks(t)
    assert report.bad_price == 1
    assert report.crossed_spread == 1
    assert report.spread_outliers == 1
    assert report.dropped == 3
    assert len(clean) == 3
    # surviving prices are untouched
    assert (clean["bid"] == 1.1000).all()


def test_price_jump_flagged():
    times = pd.date_range("2026-01-06 10:00", periods=5, freq="s", tz="UTC")
    bids = [1.1000, 1.1001, 1.1100, 1.1001, 1.1000]  # 99-pip spike at idx2
    asks = [b + 0.00007 for b in bids]
    clean, report = validate_ticks(t := _ticks(times, bids, asks), jump_pips=30.0)
    assert report.price_jumps >= 1
    assert 1.1100 not in clean["bid"].to_numpy()


def test_unordered_timestamps_counted_and_sorted():
    times = ["2026-01-06 10:00:02", "2026-01-06 10:00:01", "2026-01-06 10:00:03"]
    t = _ticks(times, [1.1, 1.1, 1.1], [1.10007, 1.10007, 1.10007])
    clean, report = validate_ticks(t)
    assert report.unordered == 1
    assert clean["time"].is_monotonic_increasing


def test_weekday_gap_flagged_weekend_gap_ignored():
    # Tuesday: 30-minute silence -> gap
    a = pd.date_range("2026-01-06 10:00", periods=10, freq="s", tz="UTC")
    b = pd.date_range("2026-01-06 10:40", periods=10, freq="s", tz="UTC")
    t = _ticks(a.append(b), np.full(20, 1.1), np.full(20, 1.10007))
    _, report = validate_ticks(t, max_gap_minutes=15)
    assert len(report.gaps) == 1

    # Friday 21:30 -> Sunday 21:30 is the FX weekend -> not a gap
    fri = pd.date_range("2026-01-09 21:20", periods=10, freq="min", tz="UTC")  # Friday
    sun = pd.date_range("2026-01-11 21:30", periods=10, freq="min", tz="UTC")  # Sunday
    t2 = _ticks(fri.append(sun), np.full(20, 1.1), np.full(20, 1.10007))
    _, report2 = validate_ticks(t2, max_gap_minutes=15)
    assert len(report2.gaps) == 0
