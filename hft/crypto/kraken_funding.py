"""Kraken Futures funding history — fetch + 8h aggregation for rung M1.5.

Kraken's PF_ perpetuals pay funding HOURLY (relativeFundingRate is the
fraction per hour). Round 1 validated the strategy on 8h-interval venues with
frozen params (enter 0.5bps/8h, exit 0, smooth 9 intervals). To evaluate
transfer WITHOUT touching those params, hourly rates are summed into UTC
00/08/16-aligned 8h buckets — same units, same cadence, same state machine.

Buckets missing hourly points (venue downtime, gaps) are dropped, not padded:
a partial bucket would understate funding and fabricating rates is what the
sanity layer exists to prevent.

Endpoint is public (no auth): /derivatives/api/v4/historicalfundingrates.
It returns roughly the trailing year, which makes any result PROVISIONAL by
construction — the pre-registered gate accounts for that.
"""

from __future__ import annotations

import json
import ssl
import urllib.request

import pandas as pd

KRAKEN_FUTURES = "https://futures.kraken.com"


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch_funding(symbol: str = "PF_XBTUSD") -> pd.DataFrame:
    """Hourly funding history, columns: time (UTC), rate (fraction per hour)."""
    url = f"{KRAKEN_FUTURES}/derivatives/api/v4/historicalfundingrates?symbol={symbol}"
    req = urllib.request.Request(url, headers={"User-Agent": "hft-harness/0.1"})
    with urllib.request.urlopen(req, timeout=30, context=_ssl_context()) as r:
        data = json.loads(r.read())
    rows = data.get("rates", [])
    df = pd.DataFrame(
        {
            "time": pd.to_datetime([x["timestamp"] for x in rows], utc=True),
            "rate": [float(x["relativeFundingRate"]) for x in rows],
        }
    )
    return df.sort_values("time", ignore_index=True)


def to_8h_intervals(hourly: pd.DataFrame, require_full: bool = True) -> pd.DataFrame:
    """Sum hourly rates into UTC 00/08/16-aligned 8h buckets.

    Returns columns time (bucket start), rate (per 8h), n_hours. With
    require_full=True only buckets with all 8 hourly points survive.
    """
    if hourly.empty:
        return pd.DataFrame(columns=["time", "rate", "n_hours"])
    t = hourly.set_index("time").sort_index()
    agg = t["rate"].resample("8h", origin="epoch").agg(["sum", "count"])
    agg = agg.rename(columns={"sum": "rate", "count": "n_hours"}).reset_index()
    if require_full:
        agg = agg[agg["n_hours"] == 8]
    else:
        agg = agg[agg["n_hours"] > 0]
    return agg.reset_index(drop=True)
