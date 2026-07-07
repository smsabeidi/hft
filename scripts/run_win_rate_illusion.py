#!/usr/bin/env python3
"""Measure the win-rate illusion on 5.5y of real EURUSD M1 bars.

Five bots, identical in every way except TP:SL geometry, all SIGNAL-FREE
(alternating direction, fixed cadence — no forecast anywhere):

  grail_2_100   tp=2   sl=100   the marketplace "99% win rate" shape
  rr_1to5      tp=10  sl=50    requested 1:5
  rr_1to3      tp=10  sl=30    requested 1:3
  symmetric    tp=20  sl=20
  inverse_3to1 tp=30  sl=10    the same coin, flipped

Two panels: frictionless (cost=0) and friendly real costs (0.25 pip spread
+ 0.7 pip commission RT + 0.1 pip slippage = 1.05 pips RT — the OPTIMISTIC
end of the round-1 cost variants, so costs can't be blamed).

Prediction from theory, written before the run: frictionless win rates track
sl/(tp+sl) with expectancy ~0 everywhere; with costs every geometry loses
~1.05 pips/trade regardless of win rate. If the harness shows anything else,
the harness is broken.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from hft.backtest.win_rate_illusion import BracketResult, BracketSpec, simulate_bracket

BARS_DIR = Path(__file__).resolve().parents[1] / "data" / "bars" / "histdata"
COST_RT_PIPS = 0.25 + 0.7 + 0.1

SPECS = [
    BracketSpec("grail_2_100", 2, 100),
    BracketSpec("rr_1to5", 10, 50),
    BracketSpec("rr_1to3", 10, 30),
    BracketSpec("symmetric", 20, 20),
    BracketSpec("inverse_3to1", 30, 10),
]


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--from-date", default=None, help="restrict window, e.g. 2025-07-01")
    ap.add_argument("--to-date", default=None)
    args = ap.parse_args()

    files = sorted(BARS_DIR.glob("EURUSD_M1_*.parquet"))
    bars = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    bars = bars.sort_values("time", ignore_index=True)
    if args.from_date:
        bars = bars[bars["time"] >= pd.Timestamp(args.from_date, tz="UTC")]
    if args.to_date:
        bars = bars[bars["time"] <= pd.Timestamp(args.to_date, tz="UTC")]
    bars = bars.reset_index(drop=True)
    print(f"EURUSD M1: {len(bars):,} bars, {bars['time'].iloc[0].date()} .. "
          f"{bars['time'].iloc[-1].date()}")

    for cost, label in [(0.0, "FRICTIONLESS (cost = 0)"),
                        (COST_RT_PIPS, f"FRIENDLY REAL COSTS ({COST_RT_PIPS:.2f} pips RT)")]:
        print("=" * 78)
        print(label)
        print(f"{'bot':>13} {'trades':>7} {'win rate':>9} {'theory':>7} "
              f"{'exp/trade':>10} {'t':>6} {'total':>9} {'maxDD':>8} {'wins/loss':>9}")
        for spec in SPECS:
            pnls = simulate_bracket(bars, spec, cost_rt_pips=cost)
            r = BracketResult.from_pnls(spec.name, pnls, spec.tp_pips, spec.sl_pips)
            theory = spec.sl_pips / (spec.tp_pips + spec.sl_pips)
            print(f"{r.name:>13} {r.trades:>7,} {r.win_rate:>8.1%} {theory:>6.1%} "
                  f"{r.expectancy_pips:>+9.2f}p {r.t_stat:>+6.1f} {r.total_pips:>+8.0f}p "
                  f"{r.max_dd_pips:>7.0f}p {r.losses_to_erase:>8.1f}")
    print("=" * 78)
    print("reading: win rate is a dial (sl/(tp+sl)) set by geometry — it moves from")
    print("25% to 98% with ZERO forecasting skill and ~zero frictionless expectancy.")
    print("Costs subtract the same ~1 pip from every shape. A '99% win rate' bot is")
    print("the first row: months of 2-pip wins, then 50 of them erased per stop hit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
