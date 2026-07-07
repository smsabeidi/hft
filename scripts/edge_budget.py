#!/usr/bin/env python3
"""Edge budget — the arithmetic that sets the trade-frequency dial.

The law: a round trip costs a FIXED number of bps (spread + fees + slippage),
but price noise over a holding period h scales as sigma(h) ~ vol * sqrt(h).
Using Grinold's first-order rule E[gross per trade] ~ IC * sigma(h) (IC =
correlation between forecast and realized return), the signal quality needed
just to BREAK EVEN is

    required IC(h)  =  cost_rt / sigma(h)  ~  1/sqrt(h).

Halving the holding period multiplies the required signal quality by ~1.41x
while the information available to a retail feed stays the same. This single
ratio is why "more trades per minute" is not a strategy parameter you are
free to turn up: frequency multiplies whatever expectancy sign you already
have, and the sign at short horizons is set by this table.

Reference points for reading the table (documented in the research doc):
top HFT firms achieve high short-horizon ICs ONLY from full-depth feeds and
microsecond reaction — the exact inputs MT5/TradingView tiers lack; classic
institutional daily-horizon signals live around IC 0.01-0.05.

Measured spreads come from the recorder's books5 files (spread distributions
are explicitly permitted QA per reports/m3_preregistration.md).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

DATA = Path(__file__).resolve().parents[1] / "data" / "crypto"

HORIZONS_MIN = [0.5, 1, 5, 15, 60, 240, 1440]

# venue presets: (label, round-trip cost bps, annual vol, traded minutes/year)
# MT5 cost: ~0.2 pip raw spread + ~0.7 pip commission-equivalent ($7/lot RT)
# on EURUSD ~= 0.9 pip ~= 0.83bp of notional; slippage/news pushes it higher.
# OKX taker: 2 legs x 5bp fees + measured spread. Maker: ~2bp RT fee proxy —
# NOTE: excludes adverse selection, which for a maker replaces the spread
# cost and is the actual game (family C6); treat maker rows as a floor.
FX_MIN_PER_YEAR = 252 * 24 * 60
CRYPTO_MIN_PER_YEAR = 365 * 24 * 60


def measured_spread_bps(inst: str, files: int = 3) -> tuple[float, int]:
    d = DATA / inst / "books5"
    paths = sorted(d.glob("*.parquet"))[-files:]
    if not paths:
        return float("nan"), 0
    df = pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)
    df = df[(df["bid1_px"] > 0) & (df["ask1_px"] > 0)]
    mid = (df["bid1_px"] + df["ask1_px"]) / 2
    spread_bps = ((df["ask1_px"] - df["bid1_px"]) / mid) * 1e4
    return float(spread_bps.mean()), len(df)


def band(ic: float) -> str:
    if ic >= 0.2:
        return "impossible at retail info/latency"
    if ic >= 0.05:
        return "top-HFT territory (needs depth+speed you lack)"
    if ic >= 0.02:
        return "institutional-hard"
    return "plausible signal class"


def main() -> int:
    btc_spread, n_btc = measured_spread_bps("BTC-USDT-SWAP")
    spread_note = (f"measured BTC perp spread {btc_spread:.2f}bp over {n_btc:,} book updates"
                   if n_btc else "no recorded books yet; using 1bp assumed spread")
    if not n_btc:
        btc_spread = 1.0
    print(spread_note)

    venues = [
        ("MT5 EURUSD raw+comm (prop tier)", 0.9, 0.08, FX_MIN_PER_YEAR),
        ("MT5 EURUSD w/ slippage+news", 1.6, 0.08, FX_MIN_PER_YEAR),
        ("OKX BTC perp TAKER (2x5bp+spread)", 10.0 + btc_spread, 0.45, CRYPTO_MIN_PER_YEAR),
        ("OKX BTC perp MAKER floor (~2bp)", 2.0, 0.45, CRYPTO_MIN_PER_YEAR),
    ]

    for label, cost_bps, vol, mpy in venues:
        print("-" * 78)
        print(f"{label}: round trip {cost_bps:.1f}bp, vol {vol:.0%}/yr")
        print(f"  {'hold':>7} {'sigma(h)':>9} {'req. IC':>8} {'max trades/day':>15}  band")
        for h in HORIZONS_MIN:
            sigma_bps = vol * math.sqrt(h / mpy) * 1e4
            ic = cost_bps / sigma_bps
            per_day = int(mpy / 365 / h)
            print(f"  {h:>6.1f}m {sigma_bps:>8.1f}bp {ic:>8.2f} {per_day:>15,}  {band(ic)}")
    print("-" * 78)
    print("reading: required IC is BREAK-EVEN signal quality (Sharpe 0). A real")
    print("strategy needs margin above it. Frequency is not free: it multiplies")
    print("the per-trade expectancy this table prices, whatever its sign.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
