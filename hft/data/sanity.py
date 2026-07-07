"""Tick data sanity validation.

The design doc's falsification principle applies to data too: a corrupt feed can
make a bad strategy look good. Every dataset passes through here before any
backtest consumes it. We DROP bad ticks; we never modify prices.

Checks:
- non-positive or NaN prices
- negative or crossed spreads (ask < bid)
- spread outliers (> outlier_mult x median spread)
- price jumps between consecutive ticks (> jump_pips)
- non-monotonic timestamps
- session gaps (no ticks for > max_gap_minutes during weekday trading hours)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class SanityReport:
    total_ticks: int = 0
    bad_price: int = 0
    crossed_spread: int = 0
    spread_outliers: int = 0
    price_jumps: int = 0
    unordered: int = 0
    gaps: list[tuple[pd.Timestamp, pd.Timestamp]] = field(default_factory=list)
    dropped: int = 0

    @property
    def issues(self) -> int:
        return (
            self.bad_price
            + self.crossed_spread
            + self.spread_outliers
            + self.price_jumps
            + self.unordered
        )

    def summary(self) -> str:
        lines = [
            f"ticks: {self.total_ticks}",
            f"bad prices: {self.bad_price}",
            f"crossed spreads: {self.crossed_spread}",
            f"spread outliers: {self.spread_outliers}",
            f"price jumps: {self.price_jumps}",
            f"unordered timestamps: {self.unordered}",
            f"session gaps: {len(self.gaps)}",
            f"dropped: {self.dropped} ({self.dropped / max(self.total_ticks, 1):.3%})",
        ]
        return "\n".join(lines)


def validate_ticks(
    ticks: pd.DataFrame,
    pip_size: float = 0.0001,
    outlier_mult: float = 10.0,
    jump_pips: float = 30.0,
    max_gap_minutes: int = 15,
) -> tuple[pd.DataFrame, SanityReport]:
    """Return (clean_ticks, report). Bad ticks are dropped, never altered."""
    report = SanityReport(total_ticks=len(ticks))
    if ticks.empty:
        return ticks.copy(), report

    t = ticks.copy()

    # timestamps must be sorted; count violations then sort
    unordered = (t["time"].diff() < pd.Timedelta(0)).sum()
    report.unordered = int(unordered)
    t = t.sort_values("time", ignore_index=True)

    bad_price = ~(np.isfinite(t["bid"]) & np.isfinite(t["ask"])) | (t["bid"] <= 0) | (t["ask"] <= 0)
    report.bad_price = int(bad_price.sum())
    t = t[~bad_price]

    spread = t["ask"] - t["bid"]
    crossed = spread < 0
    report.crossed_spread = int(crossed.sum())
    t = t[~crossed]
    spread = spread[~crossed]

    if len(t):
        med = float(spread.median())
        if med > 0:
            outlier = spread > outlier_mult * med
            report.spread_outliers = int(outlier.sum())
            t = t[~outlier]

    if len(t) > 1:
        jump = t["bid"].diff().abs() > jump_pips * pip_size
        jump.iloc[0] = False
        report.price_jumps = int(jump.sum())
        t = t[~jump]

    # session gaps: weekday stretches with no ticks. Weekend (Fri 22:00 UTC ->
    # Sun 22:00 UTC, approximately) is expected to be silent and is not flagged.
    if len(t) > 1:
        times = t["time"].reset_index(drop=True)
        deltas = times.diff()
        for i in np.flatnonzero((deltas > pd.Timedelta(minutes=max_gap_minutes)).to_numpy()):
            start, end = times.iloc[i - 1], times.iloc[i]
            if _is_weekend_gap(start, end):
                continue
            report.gaps.append((start, end))

    report.dropped = report.total_ticks - len(t)
    return t.reset_index(drop=True), report


def _is_weekend_gap(start: pd.Timestamp, end: pd.Timestamp) -> bool:
    """True when the whole gap sits inside the FX weekend close (approx UTC)."""
    fri_close_hour = 21  # conservative: some venues close 21:00-22:00 UTC Friday
    sun_open_hour = 21
    if start.dayofweek == 4 and start.hour >= fri_close_hour - 1:
        if end.dayofweek == 6 and end.hour >= sun_open_hour - 1:
            return True
        if end.dayofweek == 0 and end - start < pd.Timedelta(days=3):
            return True
    if start.dayofweek == 5 or (start.dayofweek == 6 and end.dayofweek == 6):
        return True
    return False
