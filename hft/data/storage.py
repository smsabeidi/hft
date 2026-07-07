"""Parquet storage for ticks and tick->bar aggregation.

Layout: data/ticks/{PAIR}/{YYYY-MM-DD}.parquet, one file per UTC day.
Bars are bid-quoted OHLC with per-bar mean spread so the backtester's cost
model can use the spread that actually prevailed, not a global constant.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

TICK_COLUMNS = ["time", "bid", "ask", "bid_vol", "ask_vol"]


def tick_path(root: Path, pair: str, day: str) -> Path:
    return Path(root) / "ticks" / pair.upper() / f"{day}.parquet"


def write_ticks(ticks: pd.DataFrame, root: Path, pair: str, day: str) -> Path:
    path = tick_path(root, pair, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    ticks[TICK_COLUMNS].to_parquet(path, index=False)
    return path


def read_ticks(root: Path, pair: str, days: list[str]) -> pd.DataFrame:
    frames = []
    for day in days:
        path = tick_path(root, pair, day)
        if path.exists():
            frames.append(pd.read_parquet(path))
    if not frames:
        return pd.DataFrame(columns=TICK_COLUMNS)
    out = pd.concat(frames, ignore_index=True)
    return out.sort_values("time", ignore_index=True)


def ticks_to_bars(ticks: pd.DataFrame, timeframe: str = "1min") -> pd.DataFrame:
    """Aggregate ticks to bid-quoted OHLC bars.

    Returns columns: time (bar open time, UTC), open, high, low, close (all bid),
    spread (mean ask-bid in price units), spread_max, ticks (count).
    Bars with zero ticks (weekends, gaps) are dropped, not forward-filled —
    fabricating prices is exactly what this harness exists to avoid.
    """
    if ticks.empty:
        return pd.DataFrame(
            columns=["time", "open", "high", "low", "close", "spread", "spread_max", "ticks"]
        )
    t = ticks.set_index("time").sort_index()
    spread = t["ask"] - t["bid"]
    o = t["bid"].resample(timeframe).ohlc()
    agg = pd.DataFrame(
        {
            "open": o["open"],
            "high": o["high"],
            "low": o["low"],
            "close": o["close"],
            "spread": spread.resample(timeframe).mean(),
            "spread_max": spread.resample(timeframe).max(),
            "ticks": t["bid"].resample(timeframe).count(),
        }
    )
    agg = agg[agg["ticks"] > 0]
    return agg.reset_index().rename(columns={"index": "time"})
