from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hft.backtest.costs import CostModel
from hft.risk.engine import FirmConfig, RiskEngine

PIP = 0.0001


def make_bars(
    n: int,
    seed: int = 0,
    start: str = "2026-01-05 00:00",
    start_price: float = 1.1000,
    vol_pips: float = 1.2,
    spread_pips: float = 0.7,
    freq: str = "1min",
    trend_pips_per_bar: float = 0.0,
) -> pd.DataFrame:
    """Synthetic random-walk M1 bars, bid-quoted, with a spread column."""
    rng = np.random.default_rng(seed)
    steps = rng.normal(trend_pips_per_bar * PIP, vol_pips * PIP, n)
    close = start_price + np.cumsum(steps)
    open_ = np.concatenate([[start_price], close[:-1]])
    wick = np.abs(rng.normal(0, 0.4 * PIP, n))
    high = np.maximum(open_, close) + wick
    low = np.minimum(open_, close) - wick
    time = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    return pd.DataFrame(
        {
            "time": time,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "spread": np.full(n, spread_pips * PIP),
            "spread_max": np.full(n, spread_pips * PIP),
            "ticks": np.full(n, 10),
        }
    )


def flat_bars(n: int, price: float = 1.1000, spread_pips: float = 0.7, start: str = "2026-01-05 00:00", freq: str = "1min") -> pd.DataFrame:
    """Perfectly flat bars — useful for hand-crafted scenario tests."""
    time = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    return pd.DataFrame(
        {
            "time": time,
            "open": np.full(n, price),
            "high": np.full(n, price),
            "low": np.full(n, price),
            "close": np.full(n, price),
            "spread": np.full(n, spread_pips * PIP),
            "spread_max": np.full(n, spread_pips * PIP),
            "ticks": np.full(n, 10),
        }
    )


@pytest.fixture
def cost_model() -> CostModel:
    return CostModel()


@pytest.fixture
def firm_config() -> FirmConfig:
    return FirmConfig(
        daily_loss_frac=0.05,
        total_drawdown_frac=0.10,
        max_lots=5.0,
        risk_per_trade_frac=0.005,
        daily_headroom_safety_factor=2.0,
    )


@pytest.fixture
def risk_engine(firm_config) -> RiskEngine:
    return RiskEngine(firm_config, initial_balance=50_000.0)
