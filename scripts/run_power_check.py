#!/usr/bin/env python3
"""Third validation layer: statistical POWER. The gate must say YES when a
real edge exists.

run_falsification.py proves the harness can lose (cost realism).
run_synthetic_check.py proves the gate rejects noise (false-positive control).
This script proves the gate DETECTS a planted edge (true-positive power) —
without it, a gauntlet that fails everything would look 'rigorous' while being
useless.

Construction: synthetic days with a quiet Asian session (low vol), then a
directional London drift whose direction is revealed by the first break of the
Asian range — exactly the structure SessionBreakout hypothesizes. If the full
walk-forward (param freezing, statistical gate, risk engine) cannot pass THIS,
the pipeline is over-tight and would reject real edges too.

Exit 0 = planted edge detected (gate has power). Exit 1 = gate is blind.
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
from hft.strategies.session_breakout import SessionBreakout

PIP = 0.0001


def planted_edge_bars(days: int, seed: int) -> pd.DataFrame:
    """Asian session: 0.35 pip/bar noise. 07:00-12:00 UTC: 0.8 pip/bar noise
    plus a 0.15 pip/bar drift in a per-day random direction. The drift breaks
    the Asian range in its own direction, so range breaks carry information —
    a real, detectable, tradable edge by construction."""
    rng = np.random.default_rng(seed)
    n = days * 1440
    times = pd.date_range("2025-01-06", periods=n, freq="1min", tz="UTC")
    hours = times.hour.to_numpy()
    day_index = np.arange(n) // 1440

    vol = np.where((hours >= 0) & (hours < 7), 0.35 * PIP, 0.8 * PIP)
    drift_dir = rng.choice([-1.0, 1.0], size=days)[day_index]
    drift = np.where((hours >= 7) & (hours < 12), drift_dir * 0.15 * PIP, 0.0)

    steps = rng.normal(0, 1, n) * vol + drift
    close = 1.1 + np.cumsum(steps)
    open_ = np.concatenate([[1.1], close[:-1]])
    wick = np.abs(rng.normal(0, 0.3 * PIP, n))
    return pd.DataFrame(
        {
            "time": times,
            "open": open_,
            "high": np.maximum(open_, close) + wick,
            "low": np.minimum(open_, close) - wick,
            "close": close,
            "spread": 0.7 * PIP,
        }
    )


def main() -> int:
    bars = planted_edge_bars(days=300, seed=42)
    cm = CostModel()
    cfg = FirmConfig(
        daily_loss_frac=0.05, total_drawdown_frac=0.10, max_lots=5.0, risk_per_trade_frac=0.005
    )
    res = walk_forward(
        bars,
        strategy_factory=lambda **p: SessionBreakout(**p),
        param_grid=SessionBreakout.param_grid,
        train_bars=60 * 1440,
        test_bars=20 * 1440,
        cost_model=cm,
        risk_factory=lambda: RiskEngine(cfg, 50_000.0, cm.pip_value_per_lot),
    )
    print(res.summary())
    print(res.oos_metrics.summary())
    print("-" * 60)
    if res.passed():
        print("POWER CHECK PASSED: the gauntlet detects a genuine planted edge. "
              "Combined with the falsification layers, the gate now has verified "
              "false-positive control AND true-positive power.")
        return 0
    print("POWER CHECK FAILED: a real edge was planted and the gate rejected it. "
          "The pipeline is over-tight (or the plant is below cost) — investigate "
          "before trusting any FAIL verdict on real data.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
