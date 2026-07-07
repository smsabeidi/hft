"""Recorder coverage accounting — the C5 data-floor arithmetic.

Gap/coverage scans are explicitly permitted QA under
reports/m3_preregistration.md (they carry no signal information).
The floor implemented here is the pre-registered one: a calendar day
QUALIFIES when every required instrument has >= min_coverage of its
1,440 minutes present in the books5 stream; the C5 round may run only
once >= min_days qualifying days exist spanning >= min_span_days.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

C5_INSTRUMENTS = ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "BTC-USDT", "ETH-USDT"]


def minute_coverage(data_root: Path, inst: str) -> pd.DataFrame:
    """Per-day count of distinct recorded minutes for one books5 stream."""
    files = sorted((Path(data_root) / inst / "books5").glob("*.parquet"))
    minutes: set[int] = set()
    for f in files:
        ts = pd.read_parquet(f, columns=["ts"])["ts"]
        minutes.update((ts // 60_000).unique().tolist())
    if not minutes:
        return pd.DataFrame({"date": [], "minutes": [], "coverage": []})
    s = pd.Series(sorted(minutes), dtype="int64")
    days = pd.to_datetime(s * 60_000, unit="ms", utc=True).dt.date
    per_day = days.value_counts().sort_index()
    return pd.DataFrame(
        {"date": per_day.index, "minutes": per_day.values, "coverage": per_day.values / 1440.0}
    )


@dataclass
class FloorStatus:
    qualifying_days: list
    met: bool
    detail: str


def c5_floor(
    data_root: Path,
    insts: list[str] = C5_INSTRUMENTS,
    min_days: int = 30,
    min_span_days: int = 21,
    min_coverage: float = 0.6,
) -> FloorStatus:
    per_inst = {i: minute_coverage(data_root, i).set_index("date")["coverage"] for i in insts}
    all_days = sorted(set().union(*[set(c.index) for c in per_inst.values()])) if per_inst else []
    qualifying = [
        d for d in all_days if all(c.get(d, 0.0) >= min_coverage for c in per_inst.values())
    ]
    span = (qualifying[-1] - qualifying[0]).days + 1 if qualifying else 0
    met = len(qualifying) >= min_days and span >= min_span_days
    detail = (
        f"{len(qualifying)}/{min_days} qualifying days "
        f"(>= {min_coverage:.0%} coverage on all {len(insts)} instruments), "
        f"span {span}/{min_span_days} days"
    )
    return FloorStatus(qualifying, met, detail)
