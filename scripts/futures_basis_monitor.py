#!/usr/bin/env python3
"""Futures basis monitor — the C2 decision number, live (component 1 of the
futures bot).

Reads Kraken Futures public tickers (perps + any listed fixed-maturity
contracts) against Kraken spot, computes the annualized LOCKED basis per
expiry, and compares it to the trailing realized funding (the floating
alternative) from the same venue's public history. This is the number that
justifies (or not) opening the FCM account for CME micros — re-verify on
CME's own term structure at the FCM, per the C2 study.

Cron-able daily. Decision support; trades nothing.
"""

from __future__ import annotations

import json
import ssl
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hft.crypto.kraken_funding import fetch_funding, to_8h_intervals

KRAKEN_FUTURES = "https://futures.kraken.com"
KRAKEN_SPOT = "https://api.kraken.com"
ASSETS = {"XBT": ("PF_XBTUSD", "XXBTZUSD"), "ETH": ("PF_ETHUSD", "XETHZUSD")}


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "hft-harness/0.1"})
    with urllib.request.urlopen(req, timeout=30, context=_ssl_context()) as r:
        return json.loads(r.read())


def spot_price(pair_key: str) -> float:
    out = _get(f"{KRAKEN_SPOT}/0/public/Ticker?pair={pair_key}")
    result = out["result"]
    return float(next(iter(result.values()))["c"][0])


def trailing_funding_ann(perp_symbol: str, days: int = 90) -> float | None:
    hourly = fetch_funding(perp_symbol)
    buckets = to_8h_intervals(hourly)
    if buckets.empty:
        return None
    cutoff = buckets["time"].max() - __import__("pandas").Timedelta(days=days)
    recent = buckets[buckets["time"] >= cutoff]
    span_days = max((recent["time"].max() - recent["time"].min()).days, 1)
    return float(recent["rate"].sum()) * 365 / span_days


def main() -> int:
    tickers = _get(f"{KRAKEN_FUTURES}/derivatives/api/v3/tickers").get("tickers", [])
    today = date.today()
    print(f"futures basis monitor — {datetime.now(timezone.utc).isoformat(timespec='minutes')}")

    for asset, (perp, spot_key) in ASSETS.items():
        spot = spot_price(spot_key)
        floating = trailing_funding_ann(perp)
        print("-" * 64)
        print(f"{asset}: spot {spot:,.1f} | trailing-90d realized funding "
              f"(floating alternative): "
              f"{'n/a' if floating is None else f'{floating:+.2%}/yr'}")

        fixed = []
        for t in tickers:
            sym = t.get("symbol", "")
            if not sym.upper().startswith(f"FI_{asset}USD_"):
                continue
            try:
                expiry = datetime.strptime(sym.split("_")[-1], "%y%m%d").date()
                mark = float(t.get("markPrice") or t.get("last"))
            except (ValueError, TypeError):
                continue
            dte = (expiry - today).days
            if dte <= 0:
                continue
            ann = (mark / spot - 1) * 365 / dte
            fixed.append((expiry, dte, mark, ann))

        if not fixed:
            print(f"  no fixed-maturity {asset} contracts listed on this venue — "
                  "the LOCKED-carry read needs the CME term structure (visible at "
                  "any FCM, e.g. IBKR/AMP demo). Floating side above still stands.")
            continue
        for expiry, dte, mark, ann in sorted(fixed):
            flag = ""
            if floating is not None:
                flag = "  << LOCKED BEATS FLOATING" if ann > floating else ""
            print(f"  {expiry} ({dte:>3}d): mark {mark:,.1f}, "
                  f"locked basis {ann:+.2%}/yr{flag}")
    print("-" * 64)
    print("reading: C2 enters when LOCKED annualized basis (net of ~dollar-fee")
    print("costs at CME micro scale) exceeds the floating funding it replaces.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
