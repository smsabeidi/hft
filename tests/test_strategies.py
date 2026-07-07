from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hft.backtest.costs import CostModel
from hft.backtest.engine import Backtester
from hft.risk.engine import FirmConfig, RiskEngine
from hft.strategies.mean_reversion import MeanReversion
from hft.strategies.naive_loser import RandomFlipper
from hft.strategies.session_breakout import SessionBreakout
from tests.conftest import PIP, flat_bars, make_bars


def _bt() -> Backtester:
    cfg = FirmConfig(0.05, 0.10, 5.0, 0.005)
    cm = CostModel()
    return Backtester(cm, RiskEngine(cfg, 50_000.0, cm.pip_value_per_lot), 50_000.0)


def test_random_flipper_trades_and_is_deterministic():
    bars = make_bars(2000, seed=5)
    r1 = _bt().run(bars, RandomFlipper(every_bars=30, seed=42))
    r2 = _bt().run(bars, RandomFlipper(every_bars=30, seed=42))
    assert len(r1.trades) > 10
    pd.testing.assert_frame_equal(r1.trades, r2.trades)


def test_session_breakout_goes_long_on_upside_break():
    # Asian session (00:00-06:59): flat 10-pip range. 07:00 bar closes above it.
    bars = flat_bars(600, price=1.1000, start="2026-01-05 00:00", freq="1min")
    asian = bars["time"].dt.hour < 7
    bars.loc[asian, "high"] = 1.1010
    bars.loc[asian, "low"] = 1.1000
    breakout_idx = bars.index[bars["time"].dt.hour == 7][0]
    for col in ("open", "high", "low", "close"):
        bars.loc[breakout_idx:, col] = 1.1015
    bars.loc[asian, "open"] = 1.1005
    bars.loc[asian, "close"] = 1.1005

    res = _bt().run(bars, SessionBreakout(k_tp=1.5))
    assert len(res.trades) == 1
    trade = res.trades.iloc[0]
    assert trade["side"] == 1
    # entry decided on the 07:00 close, filled next bar
    assert trade["entry_time"] == bars["time"].iloc[breakout_idx + 1]


def test_session_breakout_skips_oversized_range():
    bars = flat_bars(600, price=1.1000, start="2026-01-05 00:00", freq="1min")
    asian = bars["time"].dt.hour < 7
    bars.loc[asian, "high"] = 1.1080  # 80-pip range > max_range_pips
    bars.loc[asian, "low"] = 1.1000
    breakout_idx = bars.index[bars["time"].dt.hour == 7][0]
    for col in ("open", "high", "low", "close"):
        bars.loc[breakout_idx:, col] = 1.1090
    res = _bt().run(bars, SessionBreakout(max_range_pips=40.0))
    assert len(res.trades) == 0


def test_session_breakout_one_trade_per_day():
    bars = flat_bars(600, price=1.1000, start="2026-01-05 00:00", freq="1min")
    asian = bars["time"].dt.hour < 7
    bars.loc[asian, "high"] = 1.1010
    bars.loc[asian, "low"] = 1.1000
    idx = bars.index[bars["time"].dt.hour == 7][0]
    # whipsaw: break up, crash to stop, break up again
    for col in ("open", "high", "low", "close"):
        bars.loc[idx : idx + 30, col] = 1.1015
        bars.loc[idx + 31 : idx + 60, col] = 1.0980
        bars.loc[idx + 61 :, col] = 1.1020
    res = _bt().run(bars, SessionBreakout())
    assert len(res.trades) == 1  # second break same day is ignored


def test_mean_reversion_shorts_a_spike():
    n = 200
    bars = flat_bars(n, price=1.1000, start="2026-01-05 08:00", freq="1min")
    # 30-pip spike at bar 120 during trading hours, then it stays there
    for col in ("open", "high", "low", "close"):
        bars.loc[120:, col] = 1.1030
    res = _bt().run(bars, MeanReversion(window=60, z_in=2.5, z_out=0.5, sl_pips=50, tp_pips=60))
    assert len(res.trades) >= 1
    assert res.trades.iloc[0]["side"] == -1


def test_mean_reversion_quiet_outside_hours():
    n = 200
    bars = flat_bars(n, price=1.1000, start="2026-01-05 20:00", freq="1min")  # after hours
    for col in ("open", "high", "low", "close"):
        bars.loc[120:, col] = 1.1030
    res = _bt().run(bars, MeanReversion(window=60, trade_start_hour=7, trade_end_hour=17))
    assert len(res.trades) == 0
