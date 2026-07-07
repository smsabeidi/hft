from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hft.backtest.metrics import compute_metrics


def _trades(pnls, start="2026-01-05"):
    times = pd.date_range(start, periods=len(pnls), freq="h", tz="UTC")
    return pd.DataFrame({"pnl_usd": pnls, "exit_time": times})


def _equity(values, start="2026-01-05", freq="h"):
    times = pd.date_range(start, periods=len(values), freq=freq, tz="UTC")
    return pd.DataFrame({"time": times, "equity": values})


def test_expectancy_and_diagnostics():
    m = compute_metrics(_trades([10.0, -5.0, 10.0, -5.0]), None)
    assert m.n_trades == 4
    assert m.expectancy_usd == pytest.approx(2.5)
    assert m.total_pnl_usd == pytest.approx(10.0)
    assert m.win_rate == pytest.approx(0.5)
    assert m.profit_factor == pytest.approx(2.0)
    assert m.expectancy_ci_low < 2.5 < m.expectancy_ci_high
    assert m.t_stat > 0


def test_all_losses_profit_factor_zero():
    m = compute_metrics(_trades([-1.0, -2.0]), None)
    assert m.profit_factor == 0.0
    assert m.win_rate == 0.0


def test_empty_trades():
    m = compute_metrics(pd.DataFrame(columns=["pnl_usd"]), None)
    assert m.n_trades == 0
    assert m.expectancy_usd == 0.0


def test_max_drawdown():
    eq = _equity([100_000, 110_000, 99_000, 104_000], freq="D")
    m = compute_metrics(None, eq)
    assert m.max_drawdown_frac == pytest.approx((110_000 - 99_000) / 110_000)


def test_sharpe_positive_for_steady_gains():
    rng = np.random.default_rng(1)
    daily = 100_000 * np.cumprod(1 + np.abs(rng.normal(0.001, 0.0002, 60)))
    m = compute_metrics(None, _equity(daily.tolist(), freq="D"))
    assert m.sharpe_annual > 3.0


def test_worst_day():
    eq = _equity([100_000, 98_000, 99_000], freq="D")
    m = compute_metrics(None, eq)
    assert m.max_daily_loss_frac == pytest.approx(0.02)
