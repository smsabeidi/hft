#!/usr/bin/env python3
"""Fetch perpetual funding-rate history from Binance's public data mirror.

data.binance.vision is an open S3 archive (works even where the live API is
geo-blocked). Monthly CSVs: calc_time(ms), funding_interval_hours, rate.

This feeds the crypto-track DECISION MEMO (reports/crypto_opportunity.md):
descriptive statistics of the funding-capture opportunity, not a strategy
round — the reassessment fork (README) stays the founder's call.

Usage:
    python3 scripts/fetch_funding_binance.py --symbols BTCUSDT ETHUSDT \
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

BASE = "https://data.binance.vision/data/futures/um/monthly/fundingRate"
OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "funding"


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch_month(symbol: str, month: str) -> pd.DataFrame:
    url = f"{BASE}/{symbol}/{symbol}-fundingRate-{month}.zip"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60, context=_ssl_context()) as r:
        payload = r.read()
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        raw = zf.read(zf.namelist()[0])
    df = pd.read_csv(io.BytesIO(raw))
    df.columns = [c.strip() for c in df.columns]
    return pd.DataFrame(
        {
            "time": pd.to_datetime(df["calc_time"], unit="ms", utc=True),
            "interval_h": df["funding_interval_hours"].astype(float),
            "rate": df["last_funding_rate"].astype(float),
        }
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT"])
    ap.add_argument("--from-month", default="2021-01")
    ap.add_argument("--to-month", default="2026-06")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    months = [m.strftime("%Y-%m") for m in pd.period_range(args.from_month, args.to_month, freq="M")]
    for symbol in args.symbols:
        path = OUT_DIR / f"{symbol}_funding.parquet"
        frames, missing = [], []
        for month in months:
            try:
                frames.append(fetch_month(symbol, month))
            except Exception:
                missing.append(month)
        if not frames:
            print(f"{symbol}: nothing fetched")
            continue
        df = pd.concat(frames, ignore_index=True).sort_values("time", ignore_index=True)
        df.to_parquet(path, index=False)
        note = f" (missing months: {','.join(missing)})" if missing else ""
        print(f"{symbol}: {len(df):,} funding records "
              f"({df['time'].iloc[0].date()} .. {df['time'].iloc[-1].date()}){note} -> {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
