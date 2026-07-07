from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hft.backtest.costs import CostModel
from hft.backtest.engine import Backtester, Context
from hft.risk.engine import FirmConfig, RiskEngine
from tests.conftest import PIP, flat_bars, make_bars


def _bt(cost_model=None, **cfg_overrides) -> Backtester:
    defaults = dict(
        daily_loss_frac=0.05,
        total_drawdown_frac=0.10,
        max_lots=5.0,
        risk_per_trade_frac=0.005,
        daily_headroom_safety_factor=2.0,
    )
    defaults.update(cfg_overrides)
    cfg = FirmConfig(**defaults)
    cm = cost_model or CostModel()
    return Backtester(cm, RiskEngine(cfg, 50_000.0, cm.pip_value_per_lot), 50_000.0)


class BuyOnce:
    def __init__(self, at_bar=0, sl=10.0, tp=10.0, side=+1):
        self.at_bar, self.sl, self.tp, self.side = at_bar, sl, tp, side
        self.done = False

    def on_bar(self, ctx: Context) -> None:
        if not self.done and ctx.i == self.at_bar:
            (ctx.buy if self.side > 0 else ctx.sell)(self.sl, self.tp)
            self.done = True


class BuyThenCloseAt:
    def __init__(self, buy_bar, close_bar, sl=100.0, tp=100.0):
        self.buy_bar, self.close_bar = buy_bar, close_bar
        self.sl, self.tp = sl, tp

    def on_bar(self, ctx: Context) -> None:
        if ctx.i == self.buy_bar and ctx.position is None:
            ctx.buy(self.sl, self.tp)
        elif ctx.i == self.close_bar and ctx.position is not None:
            ctx.close()


def test_no_lookahead_fill_at_next_bar_open():
    bars = flat_bars(10, price=1.1000, spread_pips=0.7)
    bt = _bt()
    res = bt.run(bars, BuyThenCloseAt(0, 5))
    trade = res.trades.iloc[0]
    # decided on bar 0 -> filled at bar 1
    assert trade["entry_time"] == bars["time"].iloc[1]
    # entry = open(bar1) + spread + slippage = 1.1000 + 0.00007 + 0.00002
    assert trade["entry_price"] == pytest.approx(1.10009, abs=1e-9)
    # close decided bar 5 -> filled bar 6 at open - slippage
    assert trade["exit_time"] == bars["time"].iloc[6]
    assert trade["exit_price"] == pytest.approx(1.10000 - 0.00002, abs=1e-9)
    assert trade["reason"] == "close"


def test_round_trip_cost_matches_cost_model():
    bars = flat_bars(10)
    bt = _bt()
    res = bt.run(bars, BuyThenCloseAt(0, 5))
    trade = res.trades.iloc[0]
    expected = -bt.costs.round_trip_cost_usd(trade["lots"])
    assert trade["pnl_usd"] == pytest.approx(expected, rel=1e-9)


def test_stop_hit_conservative():
    bars = flat_bars(10, price=1.1000)
    # bar 3 dips 15 pips
    bars.loc[3, "low"] = 1.1000 - 15 * PIP
    bt = _bt()
    res = bt.run(bars, BuyOnce(at_bar=0, sl=10.0, tp=10.0))
    trade = res.trades.iloc[0]
    assert trade["reason"] == "stop"
    # sl price = entry - 10 pips; fill = sl - slippage (no gap: open above sl)
    entry = trade["entry_price"]
    assert trade["exit_price"] == pytest.approx(entry - 10 * PIP - 0.2 * PIP, abs=1e-9)
    assert trade["pnl_usd"] < 0


def test_stop_and_target_same_bar_means_stop():
    bars = flat_bars(10, price=1.1000)
    bars.loc[3, "low"] = 1.1000 - 15 * PIP
    bars.loc[3, "high"] = 1.1000 + 15 * PIP
    bt = _bt()
    res = bt.run(bars, BuyOnce(at_bar=0, sl=10.0, tp=10.0))
    assert res.trades.iloc[0]["reason"] == "stop"


def test_gap_through_stop_fills_at_open():
    bars = flat_bars(10, price=1.1000)
    # bar 4 gaps 50 pips down, far past the 10-pip stop
    for col in ("open", "high", "low", "close"):
        bars.loc[4, col] = 1.1000 - 50 * PIP
    bt = _bt()
    res = bt.run(bars, BuyOnce(at_bar=0, sl=10.0, tp=10.0))
    trade = res.trades.iloc[0]
    assert trade["reason"] == "stop"
    # gap: fill at the OPEN (1.0950) - slippage, not at the stop price
    assert trade["exit_price"] == pytest.approx(1.1000 - 50 * PIP - 0.2 * PIP, abs=1e-9)


def test_target_hit_long():
    bars = flat_bars(10, price=1.1000)
    bars.loc[5, "high"] = 1.1000 + 20 * PIP
    bt = _bt()
    res = bt.run(bars, BuyOnce(at_bar=0, sl=30.0, tp=10.0))
    trade = res.trades.iloc[0]
    assert trade["reason"] == "target"
    assert trade["pnl_usd"] > 0


def test_short_side_symmetry():
    bars = flat_bars(10, price=1.1000)
    bars.loc[5, "low"] = 1.1000 - 20 * PIP  # ask low = 1.0980 + spread, below tp
    bt = _bt()
    res = bt.run(bars, BuyOnce(at_bar=0, sl=30.0, tp=10.0, side=-1))
    trade = res.trades.iloc[0]
    assert trade["side"] == -1
    assert trade["reason"] == "target"
    assert trade["pnl_usd"] > 0


def test_swap_applied_across_days():
    # bars spanning midnight UTC; hold through the rollover
    bars = flat_bars(2880, price=1.1000, start="2026-01-05 12:00", freq="1min")
    bt = _bt()
    res = bt.run(bars, BuyThenCloseAt(0, 2000, sl=500.0, tp=500.0))
    trade = res.trades.iloc[0]
    assert trade["swap_usd"] != 0.0
    # long swap is negative in the default model
    assert trade["swap_usd"] < 0


def test_final_equity_equals_initial_plus_pnl():
    bars = make_bars(3000, seed=3)
    bt = _bt()
    from hft.strategies.naive_loser import RandomFlipper

    res = bt.run(bars, RandomFlipper(every_bars=50, sl_pips=8, tp_pips=8, seed=1))
    assert len(res.trades) > 5
    assert res.final_equity == pytest.approx(
        50_000.0 + res.trades["pnl_usd"].sum(), rel=1e-9
    )


def test_risk_breach_halts_and_liquidates():
    """Sizing bounds normal losses inside the daily limit; only a gap far past
    the stop (here 3x the stop distance) can break through it. When that
    happens the engine must record the violation and halt for good."""
    bars = flat_bars(20, price=1.1000)
    # bar 5: 300-pip gap down, 3x beyond the 100-pip stop
    for col in ("open", "high", "low", "close"):
        for i in range(5, 20):
            bars.loc[i, col] = 1.1000 - 300 * PIP
    bt = _bt(risk_per_trade_frac=0.04)  # oversized on purpose -> ~1.25 lots
    res = bt.run(bars, BuyOnce(at_bar=0, sl=100.0, tp=100.0))
    assert res.halted_at is not None
    assert len(res.violations) == 1
    assert res.violations[0].kind == "daily_loss"
    # the gap-through-stop realized the loss at the open, then the mark breached
    assert len(res.trades) == 1
    assert res.trades.iloc[0]["reason"] in ("stop", "risk_breach")
    assert res.final_equity < 47_500.0  # below the daily floor, as recorded


def test_entries_blocked_when_risk_engine_returns_zero():
    bars = flat_bars(10)
    bt = _bt()
    bt.risk.halted = True
    res = bt.run(bars, BuyOnce(at_bar=0))
    assert len(res.trades) == 0
