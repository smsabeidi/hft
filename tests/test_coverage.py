from __future__ import annotations

import numpy as np
import pandas as pd

from hft.crypto.coverage import c5_floor, minute_coverage


def _write_books(root, inst, day: str, minutes: int):
    """Synthetic books5 file covering `minutes` distinct minutes of one day."""
    base = pd.Timestamp(day, tz="UTC").value // 10**6
    ts = base + np.arange(minutes, dtype="int64") * 60_000
    d = root / inst / "books5"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"ts": ts, "bid1_px": 1.0, "ask1_px": 1.1}).to_parquet(
        d / f"{day}.parquet", index=False
    )


def test_minute_coverage_counts_distinct_minutes(tmp_path):
    _write_books(tmp_path, "X", "2026-07-01", 720)  # half a day
    cov = minute_coverage(tmp_path, "X")
    assert len(cov) == 1
    assert cov["coverage"].iloc[0] == 0.5


def test_floor_requires_all_instruments(tmp_path):
    insts = ["A", "B"]
    for day in pd.date_range("2026-07-01", periods=30):
        _write_books(tmp_path, "A", day.strftime("%Y-%m-%d"), 1440)
        _write_books(tmp_path, "B", day.strftime("%Y-%m-%d"), 400)  # under 60%
    status = c5_floor(tmp_path, insts=insts)
    assert not status.met  # B's poor coverage disqualifies every day


def test_floor_met_with_thirty_good_days(tmp_path):
    insts = ["A", "B"]
    for day in pd.date_range("2026-07-01", periods=30):
        for inst in insts:
            _write_books(tmp_path, inst, day.strftime("%Y-%m-%d"), 1000)  # ~69%
    status = c5_floor(tmp_path, insts=insts)
    assert status.met
    assert len(status.qualifying_days) == 30


def test_empty_dataset_not_met(tmp_path):
    status = c5_floor(tmp_path, insts=["A"])
    assert not status.met
