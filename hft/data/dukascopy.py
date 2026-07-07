"""Dukascopy free historical tick data: download and decode.

Format notes (load-bearing, verify against a known day before trusting bulk data):
- URL: https://datafeed.dukascopy.com/datafeed/{PAIR}/{YYYY}/{MM}/{DD}/{HH}h_ticks.bi5
  where MM is ZERO-BASED (January = 00). This trips everyone up once.
- Payload is LZMA-compressed. Each record is 20 bytes, big-endian:
    uint32 ms offset within the hour
    uint32 ask price scaled by 10^digits
    uint32 bid price scaled by 10^digits
    float32 ask volume (lots, indicative)
    float32 bid volume
- EURUSD uses 5 digits (scale 1e5). Empty hours return HTTP 404 or a 0-byte body;
  the feed intermittently returns 503 — treat as retryable.
"""

from __future__ import annotations

import lzma
import ssl
import struct
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

BASE_URL = "https://datafeed.dukascopy.com/datafeed"
RECORD = struct.Struct(">IIIff")


def _ssl_context() -> ssl.SSLContext:
    """macOS python.org builds ship without a CA bundle wired up; prefer
    certifi's bundle when available, fall back to the system default."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()
RECORD_SIZE = RECORD.size  # 20 bytes

# Price scale by instrument (10^digits). Extend as instruments are added.
SCALES = {
    "EURUSD": 1e5,
    "GBPUSD": 1e5,
    "USDJPY": 1e3,
    "AUDUSD": 1e5,
    "USDCHF": 1e5,
    "USDCAD": 1e5,
}


def hour_url(pair: str, dt: datetime) -> str:
    """URL for one hour of ticks. dt must be timezone-aware UTC."""
    if dt.tzinfo is None:
        raise ValueError("dt must be timezone-aware UTC")
    dt = dt.astimezone(timezone.utc)
    return (
        f"{BASE_URL}/{pair.upper()}/{dt.year:04d}/{dt.month - 1:02d}/"
        f"{dt.day:02d}/{dt.hour:02d}h_ticks.bi5"
    )


def decode_bi5(raw: bytes, pair: str, hour_start: datetime) -> pd.DataFrame:
    """Decode one hour's .bi5 payload into a tick DataFrame.

    Returns columns: time (datetime64[ns, UTC]), bid, ask, bid_vol, ask_vol.
    Empty payload -> empty frame with the right columns.
    """
    cols = ["time", "bid", "ask", "bid_vol", "ask_vol"]
    if not raw:
        return pd.DataFrame(columns=cols)
    data = lzma.decompress(raw)
    if len(data) % RECORD_SIZE != 0:
        raise ValueError(
            f"corrupt bi5 payload: {len(data)} bytes not a multiple of {RECORD_SIZE}"
        )
    n = len(data) // RECORD_SIZE
    arr = np.frombuffer(data, dtype=np.dtype(">u4, >u4, >u4, >f4, >f4"), count=n)
    scale = SCALES[pair.upper()]
    base = pd.Timestamp(hour_start).tz_convert("UTC") if pd.Timestamp(hour_start).tzinfo else pd.Timestamp(hour_start, tz="UTC")
    times = base + pd.to_timedelta(arr["f0"].astype(np.int64), unit="ms")
    return pd.DataFrame(
        {
            "time": times,
            "bid": arr["f2"].astype(np.float64) / scale,
            "ask": arr["f1"].astype(np.float64) / scale,
            "bid_vol": arr["f4"].astype(np.float64),
            "ask_vol": arr["f3"].astype(np.float64),
        }
    )


def download_hour(
    pair: str,
    dt: datetime,
    retries: int = 4,
    backoff_s: float = 2.0,
    timeout_s: float = 30.0,
) -> pd.DataFrame:
    """Download and decode one hour of ticks. 404/empty -> empty frame; 5xx retried."""
    url = hour_url(pair, dt)
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "hft-harness/0.1"})
            with urllib.request.urlopen(req, timeout=timeout_s, context=_ssl_context()) as resp:
                raw = resp.read()
            return decode_bi5(raw, pair, dt)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return decode_bi5(b"", pair, dt)
            last_err = e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = e
        time.sleep(backoff_s * (2**attempt))
    raise RuntimeError(f"failed to fetch {url} after {retries} attempts: {last_err}")


def download_day(pair: str, day: datetime, polite_delay_s: float = 0.3) -> pd.DataFrame:
    """Download all 24 hours of one UTC day. Weekend hours come back empty naturally."""
    day0 = day.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    frames = []
    for h in range(24):
        frames.append(download_hour(pair, day0 + timedelta(hours=h)))
        time.sleep(polite_delay_s)
    out = pd.concat(frames, ignore_index=True)
    return out.sort_values("time", ignore_index=True) if not out.empty else out
