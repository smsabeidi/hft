from __future__ import annotations

import lzma
import struct
from datetime import datetime, timezone

import pytest

from hft.data.dukascopy import RECORD, decode_bi5, hour_url


def _payload(records: list[tuple]) -> bytes:
    raw = b"".join(RECORD.pack(*r) for r in records)
    return lzma.compress(raw)


def test_hour_url_month_is_zero_based():
    dt = datetime(2026, 1, 5, 10, tzinfo=timezone.utc)
    url = hour_url("EURUSD", dt)
    assert "/EURUSD/2026/00/05/10h_ticks.bi5" in url


def test_hour_url_rejects_naive_datetime():
    with pytest.raises(ValueError):
        hour_url("EURUSD", datetime(2026, 1, 5, 10))


def test_decode_roundtrip():
    hour = datetime(2026, 1, 5, 10, tzinfo=timezone.utc)
    # (ms offset, ask*1e5, bid*1e5, ask_vol, bid_vol)
    payload = _payload(
        [
            (0, 110007, 110000, 1.5, 2.5),
            (1500, 110010, 110003, 0.5, 0.75),
        ]
    )
    df = decode_bi5(payload, "EURUSD", hour)
    assert len(df) == 2
    assert df["bid"].iloc[0] == pytest.approx(1.10000)
    assert df["ask"].iloc[0] == pytest.approx(1.10007)
    assert df["bid"].iloc[1] == pytest.approx(1.10003)
    assert df["time"].iloc[1].second == 1
    assert df["time"].iloc[1].microsecond == 500_000
    assert str(df["time"].dt.tz) == "UTC"
    assert df["ask_vol"].iloc[0] == pytest.approx(1.5)
    assert df["bid_vol"].iloc[0] == pytest.approx(2.5)


def test_decode_empty_payload():
    hour = datetime(2026, 1, 5, 10, tzinfo=timezone.utc)
    df = decode_bi5(b"", "EURUSD", hour)
    assert df.empty
    assert list(df.columns) == ["time", "bid", "ask", "bid_vol", "ask_vol"]


def test_decode_corrupt_payload_raises():
    hour = datetime(2026, 1, 5, 10, tzinfo=timezone.utc)
    bad = lzma.compress(b"\x00" * 21)  # not a multiple of 20
    with pytest.raises(ValueError, match="corrupt"):
        decode_bi5(bad, "EURUSD", hour)
