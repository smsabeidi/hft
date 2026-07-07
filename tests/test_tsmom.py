from __future__ import annotations

import numpy as np
import pandas as pd

from hft.backtest.costs import CostModel
from hft.backtest.engine import Backtester
from hft.risk.engine import FirmConfig, RiskEngine
from hft.strategies.tsmom import TSMOM

PIP = 0.0001


def _trend_bars(days_up: int, days_down: int, pips_per_day: float = 25.0) -> pd.DataFrame:
    """120 bars per day; price walks up for days_up days, then down."""
    rows = []
    price = 1.1000
    day0 = pd.Timestamp("2026-01-05", tz="UTC")
    for d in range(days_up + days_down):
        step = (pips_per_day if d < days_up else -pips_per_day) * PIP / 120
        for b in range(120):
            t = day0 + pd.Timedelta(days=d, minutes=10 * b)
            o = price
            price = price + step
            rows.append(
                {
                    "time": t,
                    "open": o,
                    "high": max(o, price) + 0.3 * PIP,
                    "low": min(o, price) - 0.3 * PIP,
                    "close": price,
                    "spread": 0.7 * PIP,
                }
            )
    return pd.DataFrame(rows)


def _bt() -> Backtester:
    cfg = FirmConfig(0.05, 0.10, 5.0, 0.005)
    cm = CostModel()
    return Backtester(cm, RiskEngine(cfg, 50_000.0, cm.pip_value_per_lot), 50_000.0)


def test_goes_long_in_uptrend_and_flips_after_reversal():
    bars = _trend_bars(days_up=40, days_down=40)
    strat = TSMOM(lookback_days=5, k_atr=2.0, atr_days=5)
    res = _bt().run(bars, strat)
    assert len(res.trades) >= 2
    first = res.trades.iloc[0]
    assert first["side"] == 1  # long the uptrend
    assert first["pnl_usd"] > 0  # a 40-day trend must pay a trend follower
    # exits via flip ("close"), stop, or the far target on a strong trend
    assert first["reason"] in ("close", "stop", "target")
    # and a short exists after the reversal
    assert (res.trades["side"] == -1).any()


def test_no_trades_before_warmup():
    bars = _trend_bars(days_up=4, days_down=0)  # < lookback + atr warmup
    res = _bt().run(bars, TSMOM(lookback_days=5, k_atr=2.0, atr_days=5))
    assert len(res.trades) == 0


def test_deterministic():
    bars = _trend_bars(days_up=30, days_down=30)
    r1 = _bt().run(bars, TSMOM(lookback_days=5, k_atr=2.0, atr_days=5))
    r2 = _bt().run(bars, TSMOM(lookback_days=5, k_atr=2.0, atr_days=5))
    pd.testing.assert_frame_equal(r1.trades, r2.trades)
