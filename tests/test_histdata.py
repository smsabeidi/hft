from __future__ import annotations

import io
import zipfile

import pytest

from hft.data.histdata import parse_zip


def _zip_payload(csv_text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("DAT_ASCII_EURUSD_M1_2021.csv", csv_text)
    return buf.getvalue()


def test_parse_and_est_to_utc_shift():
    # 2021-01-03 17:00 EST == 2021-01-03 22:00 UTC (Sunday FX open)
    payload = _zip_payload(
        "20210103 170000;1.223960;1.224220;1.223860;1.224220;0\n"
        "20210103 170100;1.224220;1.224500;1.224100;1.224400;0\n"
    )
    bars = parse_zip(payload)
    assert len(bars) == 2
    t0 = bars["time"].iloc[0]
    assert (t0.hour, t0.minute) == (22, 0)
    assert str(t0.tz) == "UTC"
    assert t0.dayofweek == 6  # Sunday in UTC
    assert bars["open"].iloc[0] == pytest.approx(1.223960)
    assert bars["close"].iloc[1] == pytest.approx(1.224400)


def test_parse_drops_nonpositive_and_sorts():
    payload = _zip_payload(
        "20210104 000100;1.2240;1.2241;1.2239;1.2240;0\n"
        "20210104 000000;1.2239;1.2240;1.2238;1.2239;0\n"
        "20210104 000200;0.0000;1.2241;1.2239;1.2240;0\n"
    )
    bars = parse_zip(payload)
    assert len(bars) == 2
    assert bars["time"].is_monotonic_increasing


def test_parse_rejects_zip_without_csv():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "hi")
    with pytest.raises(ValueError, match="no csv"):
        parse_zip(buf.getvalue())