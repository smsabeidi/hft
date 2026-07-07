#!/usr/bin/env python3
"""Harness gate: the falsification test (design doc, Success Criteria #1).

Runs a deliberately naive, zero-edge strategy (RandomFlipper) through the full
engine with realistic costs. The harness PASSES the gate only if the naive
strategy LOSES decisively. A harness that can't lose can't be trusted to win.

Usage:
    python3 scripts/run_falsification.py                 # synthetic random-walk data
    python3 scripts/run_falsification.py --pair EURUSD --start 2026-05-01 --end 2026-05-30
                                                          # real downloaded ticks

Exit code 0 = gate passed (naive strategy lost). Non-zero = HARNESS BROKEN.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from hft.backtest.costs import CostModel
from hft.backtest.engine import Backtester
from hft.backtest.metrics import compute_metrics
from hft.data.storage import read_ticks, ticks_to_bars
from hft.risk.engine import FirmConfig, RiskEngine
from hft.strategies.naive_loser import RandomFlipper

DATA_ROOT = Path(__file__).resolve().parents[1] / "data"


def synthetic_bars(n: int = 28_800, seed: int = 2026) -> pd.DataFrame:
    import numpy as np

    rng = np.random.default_rng(seed)
    pip = 0.0001
    steps = rng.normal(0, 1.2 * pip, n)
    close = 1.1 + np.cumsum(steps)
    open_ = np.concatenate([[1.1], close[:-1]])
    wick = np.abs(rng.normal(0, 0.4 * pip, n))
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-05", periods=n, freq="1min", tz="UTC"),
            "open": open_,
            "high": np.maximum(open_, close) + wick,
            "low": np.minimum(open_, close) - wick,
            "close": close,
            "spread": 0.7 * pip,
        }
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", default="EURUSD")
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--bars", help="parquet of pre-built bars (e.g. from fetch_yahoo_bars.py)")
    args = ap.parse_args()

    if args.bars:
        bars = pd.read_parquet(args.bars)
        source = f"bars file {args.bars} ({len(bars):,} bars)"
    elif args.start and args.end:
        days = [d.strftime("%Y-%m-%d") for d in pd.date_range(args.start, args.end)]
        ticks = read_ticks(DATA_ROOT, args.pair, days)
        if ticks.empty:
            print("no local tick data for that range; run scripts/download_data.py first")
            return 2
        bars = ticks_to_bars(ticks, "1min")
        source = f"real ticks {args.start}..{args.end} ({len(ticks):,} ticks)"
    else:
        bars = synthetic_bars()
        source = "synthetic random walk (20 trading days of M1)"

    cm = CostModel()
    # falsification measures PER-TRADE economics, not account survival: size
    # tiny (0.1% risk) so the account survives long enough to collect a
    # decisive sample. At normal sizing the risk engine (correctly) executes
    # the random gambler within days, leaving a CI too wide to conclude from.
    cfg = FirmConfig(
        daily_loss_frac=0.05, total_drawdown_frac=0.10, max_lots=5.0, risk_per_trade_frac=0.001
    )
    bt = Backtester(cm, RiskEngine(cfg, 50_000.0, cm.pip_value_per_lot), 50_000.0)
    res = bt.run(bars, RandomFlipper(every_bars=15, sl_pips=6.0, tp_pips=6.0, seed=7))
    m = compute_metrics(res.trades, res.equity)

    print(f"data: {source}")
    print(f"strategy: RandomFlipper (zero edge by construction)")
    print("-" * 60)
    print(m.summary())
    if res.halted_at is not None:
        v = res.violations[0]
        print(f"\nrisk engine halted the account at {res.halted_at} ({v.kind}) — "
              "this is the engine correctly killing a random gambler.")
    print("-" * 60)

    if m.n_trades < 30:
        print("GATE INCONCLUSIVE: fewer than 30 trades executed")
        return 3
    if m.expectancy_ci_high < 0:
        print("GATE PASSED: naive strategy loses decisively after costs. "
              "The harness can be trusted to say no.")
        return 0
    print("GATE FAILED: naive strategy did not lose — the harness or data is broken. "
          "Do NOT trust any backtest from this harness until this is fixed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
