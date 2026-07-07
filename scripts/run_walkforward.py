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
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--train-days", type=int, default=500)
    ap.add_argument("--test-days", type=int, default=120)
    args = ap.parse_args()

    days = [d.strftime("%Y-%m-%d") for d in pd.date_range(args.start, args.end)]
    ticks = read_ticks(DATA_ROOT, args.pair, days)
    if ticks.empty:
        print("no local tick data; run scripts/download_data.py first")
        return 2
    bars = ticks_to_bars(ticks, "1min")
    print(f"{len(ticks):,} ticks -> {len(bars):,} M1 bars")

    cls, grid = FAMILIES[args.strategy]
    cfg = FirmConfig(
        daily_loss_frac=0.05, total_drawdown_frac=0.10, max_lots=5.0, risk_per_trade_frac=0.005
    )
    cm = CostModel()

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
            f"range={args.start}..{args.end} scheme={args.train_days}/{args.test_days} "
            f"oos_exp={res.oos_metrics.expectancy_usd:.2f} trades={res.oos_metrics.n_trades} "
            f"stability={res.stability:.2f} result={'PASS' if res.passed() else 'FAIL'}\n"
        )
    print(f"\nround logged to {ROUNDS_LOG}")
    return 0 if res.passed() else 1


if __name__ == "__main__":
    raise SystemExit(main())
