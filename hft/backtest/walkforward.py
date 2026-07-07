"""Walk-forward validation.

Definitions (pinned in the design doc's failure policy):
- A ROUND is one complete pass over the dataset with a fixed window scheme
  (train window, test window, rolled forward by the test size).
- A round FAILS if concatenated out-of-sample expectancy is <= 0 or the result
  is unstable across windows (fraction of positive-expectancy windows below
  the stability threshold).
- Parameters are chosen ONLY on train data and frozen for the test window.
  The test windows never overlap and together form the OOS record.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Callable

import pandas as pd

from hft.backtest.costs import CostModel
from hft.backtest.engine import Backtester
from hft.backtest.metrics import Metrics, compute_metrics
from hft.risk.engine import RiskEngine


@dataclass
class WindowResult:
    train_start: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    params: dict
    train_expectancy: float
    test_expectancy: float
    test_trades: int


@dataclass
class WalkForwardResult:
    windows: list[WindowResult]
    oos_trades: pd.DataFrame
    oos_equity: pd.DataFrame  # chained across windows (no reset jumps)
    oos_metrics: Metrics
    stability: float  # fraction of ALL test windows with positive expectancy

    def passed(self, min_stability: float = 0.6) -> bool:
        return (
            self.oos_metrics.n_trades > 0
            and self.oos_metrics.expectancy_usd > 0
            and self.stability >= min_stability
        )

    def summary(self) -> str:
        status = "PASS" if self.passed() else "FAIL"
        return (
            f"walk-forward: {len(self.windows)} windows, "
            f"stability {self.stability:.0%}, OOS expectancy "
            f"${self.oos_metrics.expectancy_usd:.2f} over {self.oos_metrics.n_trades} trades -> {status}"
        )


def _grid(param_grid: dict) -> list[dict]:
    if not param_grid:
        return [{}]
    keys = list(param_grid)
    return [dict(zip(keys, vals)) for vals in product(*(param_grid[k] for k in keys))]


def walk_forward(
    bars: pd.DataFrame,
    strategy_factory: Callable[..., object],
    param_grid: dict,
    train_bars: int,
    test_bars: int,
    cost_model: CostModel,
    risk_factory: Callable[[], RiskEngine],
    initial_balance: float = 50_000.0,
) -> WalkForwardResult:
    """Rolling walk-forward. strategy_factory(**params) builds a fresh strategy.

    risk_factory must return a FRESH RiskEngine per run — risk state (halts,
    anchors) never leaks across windows.
    """
    bars = bars.reset_index(drop=True)
    if train_bars + test_bars > len(bars):
        raise ValueError(
            f"not enough bars ({len(bars)}) for train={train_bars} + test={test_bars}"
        )

    def run(segment: pd.DataFrame, params: dict) -> tuple[Metrics, pd.DataFrame]:
        bt = Backtester(cost_model, risk_factory(), initial_balance)
        res = bt.run(segment, strategy_factory(**params))
        return compute_metrics(res.trades, res.equity), res.trades

    windows: list[WindowResult] = []
    oos_frames: list[pd.DataFrame] = []
    oos_equity_frames: list[pd.DataFrame] = []
    equity_offset = 0.0  # chains window equity so Sharpe/DD see one account

    start = 0
    while start + train_bars + test_bars <= len(bars):
        train = bars.iloc[start : start + train_bars]
        test = bars.iloc[start + train_bars : start + train_bars + test_bars]

        best_params, best_exp = None, float("-inf")
        for params in _grid(param_grid):
            m, _ = run(train, params)
            score = m.expectancy_usd if m.n_trades > 0 else float("-inf")
            if score > best_exp:
                best_exp, best_params = score, params

        if best_params is None:
            # no parameter set traded in train: a zero-trade window, not a crash
            windows.append(
                WindowResult(
                    train_start=train["time"].iloc[0],
                    test_start=test["time"].iloc[0],
                    test_end=test["time"].iloc[-1],
                    params={},
                    train_expectancy=0.0,
                    test_expectancy=0.0,
                    test_trades=0,
                )
            )
            start += test_bars
            continue

        bt = Backtester(cost_model, risk_factory(), initial_balance)
        res = bt.run(test, strategy_factory(**best_params))
        test_m = compute_metrics(res.trades, res.equity)

        windows.append(
            WindowResult(
                train_start=train["time"].iloc[0],
                test_start=test["time"].iloc[0],
                test_end=test["time"].iloc[-1],
                params=best_params,
                train_expectancy=best_exp if best_exp != float("-inf") else 0.0,
                test_expectancy=test_m.expectancy_usd,
                test_trades=test_m.n_trades,
            )
        )
        if len(res.trades):
            oos_frames.append(res.trades)
        if len(res.equity):
            # rebase this window onto the prior window's ending equity so the
            # concatenated curve has no fake reset-to-initial jumps
            eq = res.equity.copy()
            eq["equity"] += equity_offset
            eq["balance"] += equity_offset
            oos_equity_frames.append(eq)
            equity_offset += res.final_equity - initial_balance
        start += test_bars

    oos_trades = (
        pd.concat(oos_frames, ignore_index=True) if oos_frames else pd.DataFrame(columns=["pnl_usd"])
    )
    oos_equity = (
        pd.concat(oos_equity_frames, ignore_index=True) if oos_equity_frames else pd.DataFrame(columns=["time", "equity"])
    )
    oos_metrics = compute_metrics(oos_trades, oos_equity)
    # zero-trade windows count AGAINST stability: params that go silent
    # out-of-sample are evidence of instability, not missing data
    stability = (
        sum(1 for w in windows if w.test_trades > 0 and w.test_expectancy > 0) / len(windows)
        if windows
        else 0.0
    )
    return WalkForwardResult(windows, oos_trades, oos_equity, oos_metrics, stability)
