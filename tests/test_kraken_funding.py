from __future__ import annotations

import pandas as pd
import pytest

from hft.crypto.kraken_funding import to_8h_intervals


def _hourly(start: str, n: int, rate: float = 1e-5) -> pd.DataFrame:
    times = pd.date_range(start, periods=n, freq="h", tz="UTC")
    return pd.DataFrame({"time": times, "rate": [rate] * n})


def test_sums_into_utc_aligned_8h_buckets():
    # 24 hourly points starting exactly at UTC midnight -> 3 full buckets
    df = to_8h_intervals(_hourly("2026-01-05 00:00", 24, rate=2e-6))
    assert len(df) == 3
    assert df["time"].iloc[0].hour == 0
    assert df["time"].iloc[1].hour == 8
    assert df["time"].iloc[2].hour == 16
    assert df["rate"].iloc[0] == pytest.approx(8 * 2e-6)
    assert (df["n_hours"] == 8).all()


def test_partial_buckets_dropped_not_padded():
    # start at 03:00 -> first bucket has only 5 of 8 hours; must be dropped
    df = to_8h_intervals(_hourly("2026-01-05 03:00", 13))
    assert len(df) == 1  # only the 08:00 bucket is full
    assert df["time"].iloc[0].hour == 8
    # opt-out keeps partials for inspection
    loose = to_8h_intervals(_hourly("2026-01-05 03:00", 13), require_full=False)
    assert len(loose) == 2
    assert loose["n_hours"].iloc[0] == 5


def test_empty_input():
    df = to_8h_intervals(pd.DataFrame(columns=["time", "rate"]))
    assert df.empty
