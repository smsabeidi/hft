#!/usr/bin/env python3
"""Fetch recent 1-minute EURUSD bars from Yahoo Finance.

HONESTY NOTE: Yahoo 1m data is indicative mid prices with no bid/ask, capped
at ~7 calendar days, with gaps. It is good for exactly one thing: smoke-testing
the pipeline on REAL market prices (the engine falls back to the cost model's
default spread). It is NOT research data — strategy validation runs on
Dukascopy ticks (scripts/download_data.py) with real recorded spreads.

Usage:
    python3 scripts/fetch_yahoo_bars.py --range 5d --out data/bars/EURUSD_yahoo_1m.parquet
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch(symbol: str = "EURUSD=X", interval: str = "1m", range_: str = "5d") -> pd.DataFrame:
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.parse.quote(symbol)}?interval={interval}&range={range_}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30, context=_ssl_context()) as r:
        data = json.loads(r.read())
    res = data["chart"]["result"][0]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame(
        {
            "time": pd.to_datetime(ts, unit="s", utc=True),
            "open": q["open"],
            "high": q["high"],
            "low": q["low"],
            "close": q["close"],
        }
    ).dropna()
    # basic sanity: strictly positive, ordered
    df = df[(df[["open", "high", "low", "close"]] > 0).all(axis=1)]
    df = df.sort_values("time", ignore_index=True)
    return df


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD=X")
    ap.add_argument("--range", dest="range_", default="5d")
    ap.add_argument("--out", default="data/bars/EURUSD_yahoo_1m.parquet")
    args = ap.parse_args()

    bars = fetch(args.symbol, "1m", args.range_)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    bars.to_parquet(out, index=False)
    print(f"{len(bars):,} real 1m bars ({bars['time'].iloc[0]} .. {bars['time'].iloc[-1]})")
    print(f"-> {out}")
    print("note: indicative mids, no spread column (engine uses default spread); "
          "smoke-test data only, not research data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
