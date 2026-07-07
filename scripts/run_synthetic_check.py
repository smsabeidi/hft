#!/usr/bin/env python3
"""Second falsification layer: strategy families must FAIL on random walks.

A random walk has no exploitable structure. If session breakout or mean
reversion "passes" a walk-forward round on synthetic random-walk data, the
harness is leaking money into strategies (lookahead, cost error, or gate
weakness) and NOTHING it says about real data can be trusted.

This complements scripts/run_falsification.py:
    falsification #1: a zero-edge STRATEGY must lose on any data.
    falsification #2 (this): a real strategy family must find NO edge in
                             structureless DATA.

Exit 0 = both families correctly fail (harness sane).
Exit 1 = a family passed on noise (HARNESS BROKEN — stop all research).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from hft.backtest.costs import CostModel
from hft.backtest.walkforward import walk_forward
from hft.risk.engine import FirmConfig, RiskEngine
from hft.strategies.mean_reversion import MeanReversion
from hft.strategies.session_breakout import SessionBreakout

PIP = 0.0001


def synthetic_bars(days: int, seed: int) -> pd.DataFrame:
    n = days * 1440
    rng = np.random.default_rng(seed)
    steps = rng.normal(0, 1.0 * PIP, n)
    close = 1.1 + np.cumsum(steps)
    open_ = np.concatenate([[1.1], close[:-1]])
    wick = np.abs(rng.normal(0, 0.4 * PIP, n))
    return pd.DataFrame(
        {
            "time": pd.date_range("2025-01-06", periods=n, freq="1min", tz="UTC"),
            "open": open_,
            "high": np.maximum(open_, close) + wick,
            "low": np.minimum(open_, close) - wick,
            "close": close,
            "spread": 0.7 * PIP,
        }
    )


def main() -> int:
    cm = CostModel()
    cfg = FirmConfig(
        daily_loss_frac=0.05, total_drawdown_frac=0.10, max_lots=5.0, risk_per_trade_frac=0.005
    )
    families = {
        "session_breakout": (lambda **p: SessionBreakout(**p), SessionBreakout.param_grid),
        "mean_reversion": (lambda **p: MeanReversion(**p), MeanReversion.param_grid),
    }

    broken = False
    for seed in (11, 29):
        bars = synthetic_bars(days=180, seed=seed)
        for name, (factory, grid) in families.items():
            res = walk_forward(
                bars,
                strategy_factory=factory,
                param_grid=grid,
                train_bars=60 * 1440,
                test_bars=20 * 1440,
                cost_model=cm,
                risk_factory=lambda: RiskEngine(cfg, 50_000.0, cm.pip_value_per_lot),
            )
            verdict = "correctly FAILED" if not res.passed() else "PASSED ON NOISE (!)"
            print(f"seed {seed} {name:>18}: {res.summary()}  -> {verdict}")
            if res.passed():
                broken = True

    print("-" * 60)
    if broken:
        print("HARNESS BROKEN: a strategy family found 'edge' in a random walk. "
              "Do not trust any result until this is explained.")
        return 1
    print("SECOND FALSIFICATION PASSED: no family finds edge in structureless data. "
          "The harness does not hallucinate profits.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
