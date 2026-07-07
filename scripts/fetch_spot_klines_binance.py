#!/usr/bin/env python3
"""Fetch Binance spot 1m klines (monthly archives) into data/bars/binance/.

Feeds the fvg_retest round-2 extension to BTCUSD. Cached per month;
timestamp unit auto-detected (2025+ archives switched to microseconds).

Usage:
    python3 scripts/fetch_spot_klines_binance.py --symbol BTCUSDT \
        --from-month 2021-01 --to-month 2026-06
"""

from __future__ import annotations

import argparse
import io
import ssl
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

BASE = "https://data.binance.vision/data/spot/monthly/klines"
OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "bars" / "binance"


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch_month(symbol: str, month: str) -> pd.DataFrame | None:
    cache = OUT_DIR / f"{symbol}-1m-{month}.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    url = f"{BASE}/{symbol}/1m/{symbol}-1m-{month}.zip"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=120, context=_ssl_context()) as r:
            payload = r.read()
    except Exception:
        return None
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        raw = zf.read(zf.namelist()[0])
    df = pd.read_csv(io.BytesIO(raw), header=None)
    if not str(df.iloc[0, 0]).lstrip("-").isdigit():
        df = df.iloc[1:].reset_index(drop=True)
    ts = df[0].astype("int64")
    unit = "us" if int(ts.iloc[0]) > 10**14 else "ms"
    out = pd.DataFrame(
        {
            "time": pd.to_datetime(ts, unit=unit, utc=True),
            "open": df[1].astype(float),
            "high": df[2].astype(float),
            "low": df[3].astype(float),
            "close": df[4].astype(float),
        }
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(cache, index=False)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--from-month", default="2021-01")
    ap.add_argument("--to-month", default="2026-06")
    args = ap.parse_args()

    months = [m.strftime("%Y-%m") for m in pd.period_range(args.from_month, args.to_month, freq="M")]
    got, missing = 0, []
    for m in months:
        df = fetch_month(args.symbol, m)
        if df is None:
            missing.append(m)
        else:
            got += 1
    print(f"{args.symbol}: {got}/{len(months)} months cached"
          + (f" (missing: {','.join(missing)})" if missing else ""))
    return 0 if got else 1


if __name__ == "__main__":
    raise SystemExit(main())
