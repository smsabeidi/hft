from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hft.data.storage import read_ticks, ticks_to_bars, write_ticks


def _ticks(n=180, start="2026-01-06 10:00"):
    times = pd.date_range(start, periods=n, freq="s", tz="UTC")
    rng = np.random.default_rng(0)
    bid = 1.1 + np.cumsum(rng.normal(0, 1e-5, n))
    return pd.DataFrame(
        {"time": times, "bid": bid, "ask": bid + 0.00007, "bid_vol": 1.0, "ask_vol": 1.0}
    )


def test_parquet_roundtrip(tmp_path):
    t = _ticks()
    write_ticks(t, tmp_path, "EURUSD", "2026-01-06")
    back = read_ticks(tmp_path, "EURUSD", ["2026-01-06", "2026-01-07"])  # second day missing
    assert len(back) == len(t)
    pd.testing.assert_series_equal(back["bid"], t["bid"], check_exact=False)


def test_read_missing_returns_empty(tmp_path):
    out = read_ticks(tmp_path, "EURUSD", ["2026-01-06"])
    assert out.empty


def test_ticks_to_bars_ohlc_and_spread():
    t = _ticks(180)  # 3 minutes of 1-second ticks
    bars = ticks_to_bars(t, "1min")
    assert len(bars) == 3
    assert (bars["ticks"] == 60).all()
    assert bars["spread"].iloc[0] == pytest.approx(0.00007)
    # OHLC of the first minute matches the raw ticks
    first_min = t.iloc[:60]["bid"]
    assert bars["open"].iloc[0] == first_min.iloc[0]
    assert bars["high"].iloc[0] == first_min.max()
    assert bars["low"].iloc[0] == first_min.min()
    assert bars["close"].iloc[0] == first_min.iloc[-1]


def test_empty_bars_dropped():
    t = _ticks(60)
    # add a tick 10 minutes later -> intermediate empty minutes must not appear
    late = t.iloc[[-1]].copy()
    late["time"] = late["time"] + pd.Timedelta(minutes=10)
    bars = ticks_to_bars(pd.concat([t, late], ignore_index=True), "1min")
    assert len(bars) == 2  # first minute + the late tick's minute, nothing fabricated
