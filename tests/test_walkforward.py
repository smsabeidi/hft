from __future__ import annotations

import pandas as pd
import pytest

from hft.backtest.costs import CostModel
from hft.backtest.walkforward import walk_forward
from hft.risk.engine import FirmConfig, RiskEngine
from hft.strategies.naive_loser import RandomFlipper
from tests.conftest import make_bars


def _risk_factory():
    cfg = FirmConfig(0.05, 0.10, 5.0, 0.005)
    return lambda: RiskEngine(cfg, 50_000.0)


def test_window_mechanics_and_param_freezing():
    bars = make_bars(3000, seed=11)
    grid = {"every_bars": [40, 80]}
    res = walk_forward(
        bars,
        strategy_factory=lambda every_bars: RandomFlipper(every_bars=every_bars, seed=3),
        param_grid=grid,
        train_bars=1000,
        test_bars=500,
        cost_model=CostModel(),
        risk_factory=_risk_factory(),
    )
    # floor((3000 - 1000) / 500) = 4 windows
    assert len(res.windows) == 4
    for w in res.windows:
        assert w.params["every_bars"] in grid["every_bars"]
        assert w.test_start > w.train_start
    # test windows are contiguous and non-overlapping
    for a, b in zip(res.windows, res.windows[1:]):
        assert b.test_start > a.test_start
        assert b.test_start > a.test_end - pd.Timedelta(minutes=1)
    # OOS trades only come from test segments
    if len(res.oos_trades):
        first_test_start = res.windows[0].test_start
        assert (res.oos_trades["entry_time"] >= first_test_start).all()
    assert 0.0 <= res.stability <= 1.0


def test_random_strategy_fails_walkforward():
    bars = make_bars(3000, seed=13)
    res = walk_forward(
        bars,
        strategy_factory=lambda every_bars: RandomFlipper(every_bars=every_bars, seed=5),
        param_grid={"every_bars": [30]},
        train_bars=1000,
        test_bars=500,
        cost_model=CostModel(),
        risk_factory=_risk_factory(),
    )
    # a no-edge strategy must not pass the round
    assert not res.passed()


class NeverTrades:
    def on_bar(self, ctx):
        pass


def test_zero_trade_train_windows_recorded_not_crashed():
    """If no parameter set trades in a train window the round must record a
    zero-trade window and keep going (review finding #9), and those windows
    must count AGAINST stability (finding #7)."""
    bars = make_bars(3000, seed=17)
    res = walk_forward(
        bars,
        strategy_factory=lambda: NeverTrades(),
        param_grid={},
        train_bars=1000,
        test_bars=500,
        cost_model=CostModel(),
        risk_factory=_risk_factory(),
    )
    assert len(res.windows) == 4
    assert all(w.test_trades == 0 for w in res.windows)
    assert res.stability == 0.0
    assert not res.passed()


def test_oos_equity_is_chained_across_windows():
    """Window equity must be rebased onto the prior window's ending equity so
    Sharpe/drawdown never see fake reset-to-initial jumps (review finding #6)."""
    bars = make_bars(3000, seed=11)
    test_bars = 500
    res = walk_forward(
        bars,
        strategy_factory=lambda every_bars: RandomFlipper(every_bars=every_bars, seed=3),
        param_grid={"every_bars": [30]},
        train_bars=1000,
        test_bars=test_bars,
        cost_model=CostModel(),
        risk_factory=_risk_factory(),
    )
    eq = res.oos_equity["equity"].to_numpy()
    assert len(eq) == len(res.windows) * test_bars
    # at every window boundary the curve must be continuous: the first mark of
    # window k (no trade filled yet) equals the final equity of window k-1
    for k in range(1, len(res.windows)):
        prev_last = eq[k * test_bars - 1]
        next_first = eq[k * test_bars]
        assert next_first == pytest.approx(prev_last, abs=1e-6)
    assert res.oos_equity["time"].is_monotonic_increasing


def test_insufficient_data_raises():
    bars = make_bars(100)
    with pytest.raises(ValueError, match="not enough bars"):
        walk_forward(
            bars,
            strategy_factory=lambda: RandomFlipper(),
            param_grid={},
            train_bars=80,
            test_bars=40,
            cost_model=CostModel(),
            risk_factory=_risk_factory(),
        )
