#!/usr/bin/env python3
"""Fetch short-rate series for the C7 carry family from FRED (public CSV).

DATA PREP + COVERAGE QA ONLY: this script fetches and caches the rate
series and prints coverage. It performs NO analysis against price data —
the C7 round is pre-registered (reports/c7_preregistration.md) and awaits
the founder's un-parking decision.

Series (3m interbank where available, else policy-rate proxy; monthly
series are forward-filled at use time — differentials move slowly):
  USD: DTB3               (3m T-bill, daily)
  EUR: ECBDFR             (ECB deposit facility rate, daily)
  GBP: IR3TIB01GBM156N    (3m interbank, monthly, OECD)
  AUD: IR3TIB01AUM156N    (3m interbank, monthly, OECD)
"""

from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

OUT = Path(__file__).resolve().parents[1] / "data" / "rates"
SERIES = {"USD": "DTB3", "EUR": "ECBDFR", "GBP": "IR3TIB01GBM156N", "AUD": "IR3TIB01AUM156N"}
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="


def fetch(series_id: str) -> pd.DataFrame:
    # curl, not urllib: FRED times out python-urllib TLS fingerprints from
    # this network (verified 2026-07-07: urllib timeout, curl 200 in 0.3s)
    proc = subprocess.run(
        ["curl", "-sS", "-m", "60", FRED + series_id],
        capture_output=True, check=True,
    )
    df = pd.read_csv(io.BytesIO(proc.stdout))
    df.columns = ["date", "rate"]
    df["date"] = pd.to_datetime(df["date"])
    df["rate"] = pd.to_numeric(df["rate"], errors="coerce")
    return df.dropna().reset_index(drop=True)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ok = True
    for ccy, sid in SERIES.items():
        try:
            df = fetch(sid)
        except Exception as e:
            print(f"{ccy} ({sid}): FETCH FAILED — {type(e).__name__}: {str(e)[:60]}")
            ok = False
            continue
        path = OUT / f"{ccy}_{sid}.parquet"
        df.to_parquet(path, index=False)
        recent = df[df["date"] >= "2021-01-01"]
        print(f"{ccy} ({sid}): {len(df):,} obs, {df['date'].iloc[0].date()} .. "
              f"{df['date'].iloc[-1].date()} | 2021+: {len(recent):,} obs, "
              f"latest {df['rate'].iloc[-1]:.2f}%")
    if not ok:
        print("\nsome legs missing — per the pre-registration, pair-periods without "
              "rate data are untraded, or source an alternative before the round.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
