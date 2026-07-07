#!/usr/bin/env python3
"""Run a single backtest of one strategy family and export the trade log.

The exported trades CSV is the Python-side input to the parity gate
(scripts/parity_check.py). Metrics print to stdout.

Usage:
    python3 scripts/run_backtest.py --strategy session_breakout \
        --pair EURUSD --start 2026-05-01 --end 2026-06-30 \
        --params '{"k_tp": 1.5, "max_range_pips": 40.0}' \
        --out reports/py_trades.csv
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from hft.backtest.costs import CostModel
from hft.backtest.engine import Backtester
from hft.backtest.metrics import compute_metrics
from hft.data.storage import read_ticks, ticks_to_bars
from hft.risk.engine import FirmConfig, RiskEngine
from hft.strategies.mean_reversion import MeanReversion
from hft.strategies.session_breakout import SessionBreakout

DATA_ROOT = Path(__file__).resolve().parents[1] / "data"

FAMILIES = {
    "session_breakout": SessionBreakout,
    "mean_reversion": MeanReversion,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True, choices=sorted(FAMILIES))
    ap.add_argument("--pair", default="EURUSD")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--params", default="{}", help="JSON dict of strategy params")
    ap.add_argument("--out", default="reports/py_trades.csv")
    ap.add_argument("--balance", type=float, default=50_000.0)
    args = ap.parse_args()

    days = [d.strftime("%Y-%m-%d") for d in pd.date_range(args.start, args.end)]
    ticks = read_ticks(DATA_ROOT, args.pair, days)
    if ticks.empty:
        print("no local tick data; run scripts/download_data.py first")
        return 2
    bars = ticks_to_bars(ticks, "1min")
    print(f"{len(ticks):,} ticks -> {len(bars):,} M1 bars")

    cm = CostModel()
    cfg = FirmConfig(
        daily_loss_frac=0.05, total_drawdown_frac=0.10, max_lots=5.0, risk_per_trade_frac=0.005
    )
    bt = Backtester(cm, RiskEngine(cfg, args.balance, cm.pip_value_per_lot), args.balance)
    strategy = FAMILIES[args.strategy](**json.loads(args.params))
    res = bt.run(bars, strategy)
    m = compute_metrics(res.trades, res.equity)

    print(m.summary())
    if res.halted_at is not None:
        print(f"\nRISK BREACH at {res.halted_at}: {res.violations[0].kind} — this "
              "configuration would have killed the account.")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    res.trades.to_csv(out, index=False)
    res.equity.to_csv(out.with_name(out.stem + "_equity.csv"), index=False)
    print(f"\ntrades -> {out}\nequity -> {out.with_name(out.stem + '_equity.csv')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
