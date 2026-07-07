"""HistData.com free M1 forex history: download and parse.

Data notes (load-bearing):
- Format: generic ASCII M1, one row per traded minute:
      20210103 170000;1.223960;1.224220;1.223860;1.224220;0
  separator ';', volume always 0.
- TIMEZONE: HistData timestamps are EST (UTC-5) FIXED, no DST — chosen so the
  trading week runs Sun 17:00 to Fri 17:00. UTC = timestamp + 5 hours. Getting
  this wrong shifts every session strategy by hours, silently.
- No bid/ask: OHLC only. The engine falls back to the cost model's default
  spread. This makes HistData research-grade-MINUS: real prices, modeled
  spreads. Results stand provisionally until re-run on Dukascopy ticks with
  real recorded spreads (design doc: cost model recalibration per transition).
"""

from __future__ import annotations

import io
import re
import ssl
import urllib.parse
import urllib.request
import zipfile

import pandas as pd

BASE = "https://www.histdata.com"
PAGE = BASE + "/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes"
EST_OFFSET = pd.Timedelta(hours=5)  # EST (fixed, no DST) -> UTC


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _get(url: str, timeout: float = 60.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as r:
        return r.read()


def _post(url: str, data: dict, referer: str, timeout: float = 180.0) -> bytes:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": referer,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as r:
        return r.read()


def download_m1(pair: str, year: int, month: int | None = None) -> bytes:
    """Download one year (or one month of the current year) as a zip payload."""
    slug = pair.lower()
    if month is None:
        page_url = f"{PAGE}/{slug}/{year}"
        datemonth = str(year)
    else:
        page_url = f"{PAGE}/{slug}/{year}/{month}"
        datemonth = f"{year}{month:02d}"
    html = _get(page_url).decode("utf-8", "ignore")
    m = re.search(r'name="tk"\s+id="tk"\s+value="([a-f0-9]+)"', html)
    if not m:
        raise RuntimeError(f"no download token on {page_url} (page layout changed?)")
    return _post(
        BASE + "/get.php",
        {
            "tk": m.group(1),
            "date": str(year),
            "datemonth": datemonth,
            "platform": "ASCII",
            "timeframe": "M1",
            "fxpair": pair.upper(),
        },
        referer=page_url,
    )


def parse_zip(payload: bytes) -> pd.DataFrame:
    """Parse a HistData ASCII M1 zip into UTC bars (no spread column)."""
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not csv_names:
            raise ValueError(f"no csv in zip (contents: {zf.namelist()})")
        raw = zf.read(csv_names[0])
    df = pd.read_csv(
        io.BytesIO(raw),
        sep=";",
        header=None,
        names=["ts", "open", "high", "low", "close", "vol"],
        dtype={"ts": str},
    )
    time = pd.to_datetime(df["ts"], format="%Y%m%d %H%M%S") + EST_OFFSET
    out = pd.DataFrame(
        {
            "time": time.dt.tz_localize("UTC"),
            "open": df["open"].astype(float),
            "high": df["high"].astype(float),
            "low": df["low"].astype(float),
            "close": df["close"].astype(float),
        }
    )
    out = out[(out[["open", "high", "low", "close"]] > 0).all(axis=1)]
    return out.sort_values("time", ignore_index=True)
