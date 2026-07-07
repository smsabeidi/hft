#!/usr/bin/env python3
"""Run a walk-forward round for one strategy family on local tick data.

Usage:
    python3 scripts/run_walkforward.py --strategy session_breakout \
        --pair EURUSD --start 2021-01-04 --end 2026-06-30 \
        --train-days 500 --test-days 120

A ROUND (design doc definition): one complete pass with a fixed window scheme.
It FAILS if OOS expectancy <= 0 or stability < 60%. Two failed rounds kill the
family — track your rounds in reports/rounds.log (appended automatically).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from hft.backtest.costs import CostModel
from hft.backtest.walkforward import walk_forward
from hft.data.storage import read_ticks, ticks_to_bars
from hft.risk.engine import FirmConfig, RiskEngine
from hft.strategies.mean_reversion import MeanReversion
from hft.strategies.session_breakout import SessionBreakout

DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
ROUNDS_LOG = Path(__file__).resolve().parents[1] / "reports" / "rounds.log"

FAMILIES = {
    "session_breakout": (SessionBreakout, SessionBreakout.param_grid),
    "mean_reversion": (MeanReversion, MeanReversion.param_grid),
}

BARS_PER_TRADING_DAY = 1440  # M1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True, choices=sorted(FAMILIES))
    ap.add_argument("--pair", default="EURUSD")
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--bars-glob", help="glob of bar parquets (e.g. data/bars/histdata/*.parquet)")
    ap.add_argument("--train-days", type=int, default=500)
    ap.add_argument("--test-days", type=int, default=120)
    ap.add_argument("--spread-pips", type=float, default=0.7,
                    help="default spread when bars carry none (cost sensitivity)")
    ap.add_argument("--slippage-pips", type=float, default=0.2)
    args = ap.parse_args()

    if args.bars_glob:
        import glob as glob_mod

        files = sorted(glob_mod.glob(args.bars_glob))
        if not files:
            print(f"no files match {args.bars_glob}")
            return 2
        bars = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
        bars = bars.sort_values("time", ignore_index=True)
        print(f"{len(files)} files -> {len(bars):,} M1 bars "
              f"({bars['time'].iloc[0].date()} .. {bars['time'].iloc[-1].date()})")
        if "spread" not in bars.columns:
            print("note: no spread column — engine uses the cost model's default "
                  "spread; results provisional until re-run on Dukascopy ticks.")
        data_range = f"{bars['time'].iloc[0].date()}..{bars['time'].iloc[-1].date()}"
    else:
        if not (args.start and args.end):
            ap.error("provide --bars-glob or --start/--end")
        days = [d.strftime("%Y-%m-%d") for d in pd.date_range(args.start, args.end)]
        ticks = read_ticks(DATA_ROOT, args.pair, days)
        if ticks.empty:
            print("no local tick data; run scripts/download_data.py first")
            return 2
        bars = ticks_to_bars(ticks, "1min")
        print(f"{len(ticks):,} ticks -> {len(bars):,} M1 bars")
        data_range = f"{args.start}..{args.end}"

    cls, grid = FAMILIES[args.strategy]
    cfg = FirmConfig(
        daily_loss_frac=0.05, total_drawdown_frac=0.10, max_lots=5.0, risk_per_trade_frac=0.005
    )
    cm = CostModel(default_spread_pips=args.spread_pips, slippage_pips=args.slippage_pips)

    res = walk_forward(
        bars,
        strategy_factory=lambda **p: cls(**p),
        param_grid=grid,
        train_bars=args.train_days * BARS_PER_TRADING_DAY,
        test_bars=args.test_days * BARS_PER_TRADING_DAY,
        cost_model=cm,
        risk_factory=lambda: RiskEngine(cfg, 50_000.0, cm.pip_value_per_lot),
    )

    print(res.summary())
    for w in res.windows:
        print(
            f"  {w.test_start.date()} -> {w.test_end.date()}  params={w.params}  "
            f"train_exp=${w.train_expectancy:.2f}  test_exp=${w.test_expectancy:.2f}  "
            f"({w.test_trades} trades)"
        )
    print()
    print(res.oos_metrics.summary())

    ROUNDS_LOG.parent.mkdir(exist_ok=True)
    with ROUNDS_LOG.open("a") as f:
        f.write(
            f"{datetime.now(timezone.utc).isoformat()} family={args.strategy} "
            f"range={data_range} scheme={args.train_days}/{args.test_days} "
            f"costs={args.spread_pips}sp/{args.slippage_pips}sl "
            f"oos_exp={res.oos_metrics.expectancy_usd:.2f} t={res.oos_metrics.t_stat:.2f} "
            f"trades={res.oos_metrics.n_trades} "
            f"stability={res.stability:.2f} result={'PASS' if res.passed() else 'FAIL'}\n"
        )
    print(f"\nround logged to {ROUNDS_LOG}")
    return 0 if res.passed() else 1


if __name__ == "__main__":
    raise SystemExit(main())
