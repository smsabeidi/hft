#!/usr/bin/env python3
"""C2 — fixed-expiry basis vs floating funding (research doc §5, candidate C2).

Decision-support STUDY (like reports/crypto_opportunity.md), not a strategy
round: it feeds the Branch-A venue decision, so it reports to the founder and
does not write to rounds.log.

Question: entering a cash-and-carry at date t (long spot, short quarterly
future expiring at E) LOCKS an annualized carry of (F/S - 1) * 365/dte at
entry. The floating alternative (short perp, collect funding over [t, E])
realizes whatever funding turns out to be. Which was better, when, and by
how much — on the same windows?

Data: Binance USDT-margined quarterly delivery futures (BTCUSDT_YYMMDD,
ETHUSDT_YYMMDD) daily closes + spot daily closes + the funding history
already in data/funding/. Binance is the PROXY here — the trade this informs
is CME micro futures vs onshore spot (M1 brief, Branch A); CME basis is
typically fatter (futures-led venue), so re-verify on CME quotes at decision
time. Proxy limitation stated up front.

Reported, per entry year: median/IQR of locked annualized basis (14-120 days
to expiry) vs realized annualized funding carry over the identical windows,
and the win rate of locked-vs-floating.
"""

from __future__ import annotations

import io
import ssl
import sys
import urllib.request
import zipfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FUNDING_DIR = ROOT / "data" / "funding"
BASIS_DIR = FUNDING_DIR / "quarterly"
UM_BASE = "https://data.binance.vision/data/futures/um/monthly/klines"
SPOT_BASE = "https://data.binance.vision/data/spot/monthly/klines"

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
FIRST_EXPIRY_YEAR, LAST_EXPIRY = 2021, "2026-09"
DTE_MIN, DTE_MAX = 14, 120


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def last_friday(year: int, month: int) -> date:
    d = date(year, month, 1) + timedelta(days=32)
    d = d.replace(day=1) - timedelta(days=1)  # last day of month
    return d - timedelta(days=(d.weekday() - 4) % 7)


def quarterly_expiries() -> list[date]:
    out = []
    last = pd.Period(LAST_EXPIRY, freq="M")
    for year in range(FIRST_EXPIRY_YEAR, last.year + 1):
        for month in (3, 6, 9, 12):
            if pd.Period(f"{year}-{month:02d}", freq="M") <= last:
                out.append(last_friday(year, month))
    return out


def fetch_daily_klines(url_base: str, symbol: str, month: str) -> pd.DataFrame | None:
    cache = BASIS_DIR / f"{symbol}-1d-{month}.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    url = f"{url_base}/{symbol}/1d/{symbol}-1d-{month}.zip"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=60, context=_ssl_context()) as r:
            payload = r.read()
    except Exception:
        return None
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        raw = zf.read(zf.namelist()[0])
    df = pd.read_csv(io.BytesIO(raw), header=None)
    if not str(df.iloc[0, 0]).lstrip("-").isdigit():
        df = df.iloc[1:].reset_index(drop=True)
    ts = df[0].astype("int64")
    unit = "us" if int(ts.iloc[0]) > 10**14 else "ms"  # 2025+ spot archives use microseconds
    out = pd.DataFrame(
        {
            "day": pd.to_datetime(ts, unit=unit, utc=True).dt.date,
            "close": df[4].astype(float),
        }
    )
    BASIS_DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(cache, index=False)
    return out


def load_series(url_base: str, symbol: str, months: list[str]) -> pd.Series:
    frames = [f for m in months if (f := fetch_daily_klines(url_base, symbol, m)) is not None]
    if not frames:
        return pd.Series(dtype=float)
    df = pd.concat(frames, ignore_index=True).drop_duplicates("day")
    return df.set_index("day")["close"].sort_index()


def realized_funding_ann(funding: pd.DataFrame, start: date, expiry: date) -> float | None:
    window = funding[
        (funding["time"].dt.date >= start) & (funding["time"].dt.date < expiry)
    ]
    if len(window) < (expiry - start).days:  # sanity: ~3 events/day expected
        return None
    days = (expiry - start).days
    return float(window["rate"].sum()) * 365 / days


def main() -> int:
    rows = []
    for sym in SYMBOLS:
        funding = pd.read_parquet(FUNDING_DIR / f"{sym}_funding.parquet")
        spot_months = [m.strftime("%Y-%m") for m in pd.period_range("2021-01", "2026-06", freq="M")]
        spot = load_series(SPOT_BASE, sym, spot_months)
        for expiry in quarterly_expiries():
            contract = f"{sym}_{expiry.strftime('%y%m%d')}"
            months = [
                m.strftime("%Y-%m")
                for m in pd.period_range(
                    pd.Period(expiry.strftime("%Y-%m")) - 7, expiry.strftime("%Y-%m"), freq="M"
                )
            ]
            fut = load_series(UM_BASE, contract, months)
            if fut.empty:
                continue
            for day, f_close in fut.items():
                dte = (expiry - day).days
                if not (DTE_MIN <= dte <= DTE_MAX) or day not in spot.index:
                    continue
                locked = (f_close / spot[day] - 1) * 365 / dte
                floating = realized_funding_ann(funding, day, expiry)
                if floating is None:
                    continue
                rows.append(
                    {
                        "symbol": sym, "contract": contract, "day": day, "dte": dte,
                        "locked_ann": locked, "floating_ann": floating,
                    }
                )
        print(f"{sym}: {sum(1 for r in rows if r['symbol'] == sym)} contract-days")

    df = pd.DataFrame(rows)
    if df.empty:
        print("no data assembled — nothing to report")
        return 1
    df.to_parquet(FUNDING_DIR / "c2_basis_vs_funding.parquet", index=False)

    df["year"] = pd.to_datetime(df["day"].astype(str)).dt.year
    df["locked_wins"] = df["locked_ann"] > df["floating_ann"]
    print("-" * 88)
    print("annualized carry, locked (quarterly basis at entry) vs floating (realized funding),")
    print("entry windows with 14-120 days to expiry, pooled BTC+ETH:")
    print(f"{'year':>6} {'n':>5} {'locked med':>11} {'locked IQR':>17} "
          f"{'floating med':>13} {'locked wins':>12}")
    for year, g in df.groupby("year"):
        q1, q3 = g["locked_ann"].quantile([0.25, 0.75])
        print(f"{year:>6} {len(g):>5} {g['locked_ann'].median():>10.1%} "
              f"[{q1:>6.1%}, {q3:>6.1%}] {g['floating_ann'].median():>12.1%} "
              f"{g['locked_wins'].mean():>11.0%}")
    q1, q3 = df["locked_ann"].quantile([0.25, 0.75])
    print(f"{'all':>6} {len(df):>5} {df['locked_ann'].median():>10.1%} "
          f"[{q1:>6.1%}, {q3:>6.1%}] {df['floating_ann'].median():>12.1%} "
          f"{df['locked_wins'].mean():>11.0%}")
    print("\nnote: proxy data (Binance delivery futures); the actionable trade is CME micro")
    print("futures vs onshore spot — re-verify levels on CME term structure at decision time.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
