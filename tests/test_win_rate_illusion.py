"""The falsification property behind the win-rate illusion demo: on a
signal-free random walk, geometry sets win rate while costs set expectancy.
If the simulator ever shows a high-win-rate bracket EARNING money on noise,
the simulator is broken."""

from __future__ import annotations

import numpy as np
import pandas as pd

from hft.backtest.win_rate_illusion import BracketSpec, simulate_bracket

PIP = 0.0001


def _random_walk_bars(n=200_000, seed=3):
    rng = np.random.default_rng(seed)
    mid = 1.10 + np.cumsum(rng.normal(0, 1.2 * PIP, n))
    o = mid
    c = np.roll(mid, -1)
    c[-1] = mid[-1]
    wiggle = np.abs(rng.normal(0, 0.8 * PIP, n))
    return pd.DataFrame(
        {
            "time": pd.date_range("2024-01-01", periods=n, freq="1min", tz="UTC"),
            "open": o,
            "high": np.maximum(o, c) + wiggle,
            "low": np.minimum(o, c) - wiggle,
            "close": c,
        }
    )


def test_grail_geometry_high_win_rate_negative_expectancy():
    bars = _random_walk_bars()
    pnls = simulate_bracket(bars, BracketSpec("grail", 2, 100), cost_rt_pips=1.05)
    assert len(pnls) > 500
    win_rate = (pnls > 0).mean()
    assert win_rate > 0.90            # the illusion: geometry alone
    assert pnls.mean() < 0            # the reality: costs set the sign


def test_frictionless_random_walk_is_fair_game():
    bars = _random_walk_bars(seed=9)
    for tp, sl in [(2, 100), (20, 20), (30, 10)]:
        pnls = simulate_bracket(bars, BracketSpec("x", tp, sl), cost_rt_pips=0.0)
        assert len(pnls) > 300
        # no geometry manufactures expectancy on noise (loose bound, it's noise)
        assert abs(pnls.mean()) < 1.0


def test_win_rate_tracks_geometry_not_skill():
    bars = _random_walk_bars(seed=5)
    for tp, sl in [(2, 100), (10, 30), (30, 10)]:
        pnls = simulate_bracket(bars, BracketSpec("x", tp, sl), cost_rt_pips=0.0)
        theory = sl / (tp + sl)
        assert abs((pnls > 0).mean() - theory) < 0.06
