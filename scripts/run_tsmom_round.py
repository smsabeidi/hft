#!/usr/bin/env python3
"""Round 1 for the TSMOM family: pooled across USD-quote pairs.

Single-pair daily momentum can't reach the 100-trade OOS sample the gate
demands, so the round pools OOS trades across EURUSD, GBPUSD, AUDUSD (all
USD-quote, so the $10/pip/lot cost model holds). Each pair runs its own
walk-forward (params frozen per window per pair); the gate applies to the
POOLED result: >=100 OOS trades, pooled expectancy > 0, pooled t >= 2.0,
stability across ALL pair-windows >= 60%.

Pooled Sharpe/drawdown are per-account metrics and not meaningful across
parallel simulated accounts — expectancy and t carry the verdict.
"""

from __future__ import annotations

import glob
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from scipy import stats

from hft.backtest.costs import CostModel
from hft.backtest.walkforward import walk_forward
from hft.risk.engine import FirmConfig, RiskEngine
from hft.strategies.tsmom import TSMOM

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "bars" / "histdata"
ROUNDS_LOG = Path(__file__).resolve().parents[1] / "reports" / "rounds.log"
PAIRS = ["EURUSD", "GBPUSD", "AUDUSD"]


def main() -> int:
    cm = CostModel()
    cfg = FirmConfig(
        daily_loss_frac=0.05, total_drawdown_frac=0.10, max_lots=5.0, risk_per_trade_frac=0.005
    )

    all_trades = []
    all_windows = []
    for pair in PAIRS:
        files = sorted(glob.glob(str(DATA_DIR / f"{pair}_M1_*.parquet")))
        if not files:
            print(f"{pair}: no data, skipping")
            continue
        bars = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
        bars = bars.sort_values("time", ignore_index=True)
        res = walk_forward(
            bars,
            strategy_factory=lambda **p: TSMOM(**p),
            param_grid=TSMOM.param_grid,
            train_bars=500 * 1440,
            test_bars=120 * 1440,
            cost_model=cm,
            risk_factory=lambda: RiskEngine(cfg, 50_000.0, cm.pip_value_per_lot),
        )
        print(f"{pair}: {res.summary()}")
        for w in res.windows:
            print(f"    {w.test_start.date()} -> {w.test_end.date()}  {w.params}  "
                  f"test_exp=${w.test_expectancy:.2f} ({w.test_trades} trades)")
        if len(res.oos_trades):
            all_trades.append(res.oos_trades.assign(pair=pair))
        all_windows.extend(res.windows)

    if not all_trades:
        print("no OOS trades anywhere -> FAIL")
        return 1

    pooled = pd.concat(all_trades, ignore_index=True)
    pnl = pooled["pnl_usd"].to_numpy(dtype=float)
    n = len(pnl)
    exp = float(pnl.mean())
    t_stat = float(exp / (pnl.std(ddof=1) / np.sqrt(n))) if n > 1 and pnl.std(ddof=1) > 0 else 0.0
    lo, hi = (
        stats.t.interval(0.95, df=n - 1, loc=exp, scale=pnl.std(ddof=1) / np.sqrt(n))
        if n > 1
        else (exp, exp)
    )
    stability = (
        sum(1 for w in all_windows if w.test_trades > 0 and w.test_expectancy > 0)
        / len(all_windows)
        if all_windows
        else 0.0
    )
    passed = n >= 100 and exp > 0 and t_stat >= 2.0 and stability >= 0.6

    print("-" * 60)
    print(f"POOLED ({'+'.join(PAIRS)}): {n} OOS trades, expectancy ${exp:.2f} "
          f"(95% CI [{lo:.2f}, {hi:.2f}], t={t_stat:.2f}), "
          f"window stability {stability:.0%}")
    print(f"per-pair expectancy: " + "  ".join(
        f"{p}=${g['pnl_usd'].mean():.2f}({len(g)})" for p, g in pooled.groupby("pair")
    ))
    print(f"STRATEGY GATE: {'PASS' if passed else 'FAIL'}")

    ROUNDS_LOG.parent.mkdir(exist_ok=True)
    with ROUNDS_LOG.open("a") as f:
        f.write(
            f"{datetime.now(timezone.utc).isoformat()} family=tsmom_pooled "
            f"range=2021-01..2026-06 scheme=500/120 costs=0.7sp/0.2sl "
            f"oos_exp={exp:.2f} t={t_stat:.2f} trades={n} "
            f"stability={stability:.2f} result={'PASS' if passed else 'FAIL'}\n"
        )
    print(f"round logged to {ROUNDS_LOG}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
