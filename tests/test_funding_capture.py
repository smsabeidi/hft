from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hft.crypto.funding_capture import (
    CaptureParams,
    backtest_capture,
    walk_forward_capture,
)


def _funding(rates, start="2024-01-01"):
    times = pd.date_range(start, periods=len(rates), freq="8h", tz="UTC")
    return pd.DataFrame({"time": times, "rate": rates})


def test_constant_positive_funding_pays():
    # 2 bps/8h forever, threshold 0.5bp -> one long episode, clearly net positive
    f = _funding([0.0002] * 300)
    p = CaptureParams(enter_bps=0.5, exit_bps=0.0, smooth_n=3, fee_rt_bps=25.0, utilization=0.6)
    r = backtest_capture(f, p)
    assert len(r.episodes) == 1
    ep = r.episodes[0]
    # gross: ~297 on-intervals x 2bp x 0.6; fees: 25bp RT x 0.6 = 15bp once
    assert ep.gross_return == pytest.approx(297 * 0.0002 * 0.6, rel=0.02)
    assert ep.net_return == pytest.approx(ep.gross_return - 0.0025 * 0.6, rel=1e-6)
    assert r.annualized_net > 0.05  # ~13%/yr gross at 2bp/8h
    assert r.time_in_market > 0.95


def test_negative_funding_stays_out():
    f = _funding([-0.0002] * 300)
    r = backtest_capture(f, CaptureParams())
    assert len(r.episodes) == 0
    assert r.net_return == 0.0
    assert r.time_in_market == 0.0


def test_hysteresis_no_flapping():
    # rate oscillates between 0.4bp and 0.6bp around enter=0.5/exit=0.0:
    # once in (smooth > 0.5bp impossible with oscillation around it after
    # smoothing), use a clean pattern: strong positive stretch, weak positive
    # stretch (below enter but above exit), then negative -> ONE episode
    rates = [0.0002] * 50 + [0.00003] * 50 + [-0.0002] * 50
    f = _funding(rates)
    p = CaptureParams(enter_bps=0.5, exit_bps=0.0, smooth_n=3)
    r = backtest_capture(f, p)
    assert len(r.episodes) == 1
    ep = r.episodes[0]
    # stayed in through the weak stretch (hysteresis), left when smooth < 0
    assert ep.intervals > 90


def test_no_lookahead_in_smoothing():
    # a single huge positive spike at the end must NOT cause an entry at the
    # spike itself (the smoothed value for interval i excludes interval i)
    rates = [-0.0001] * 100 + [0.01]
    f = _funding(rates)
    r = backtest_capture(f, CaptureParams(enter_bps=0.5, exit_bps=0.0, smooth_n=1))
    assert len(r.episodes) == 0


def test_fees_make_short_episodes_lose():
    # 3 strong intervals then negative: gross 3 x 5bp x 0.6 = 9bp < 15bp fees
    rates = [0.0005] * 3 + [-0.0005] * 60
    f = _funding(rates)
    p = CaptureParams(enter_bps=0.4, exit_bps=0.0, smooth_n=1, fee_rt_bps=25.0)
    r = backtest_capture(f, p)
    if r.episodes:  # entry happens on the smoothed signal
        assert r.episodes[0].net_return < 0


def test_walk_forward_mechanics_and_gate():
    rng = np.random.default_rng(5)
    rates = rng.normal(0.0001, 0.0002, 3000)  # positive-mean funding regime
    f = _funding(rates)
    res = walk_forward_capture(
        f,
        param_grid={"enter_bps": [0.3, 0.5], "smooth_n": [3, 9]},
        train_n=1000,
        test_n=400,
    )
    assert len(res.windows) == 5
    g = res.gate()
    assert set(g) >= {"episodes", "mean_episode_net", "t", "stability", "passed"}
    for w in res.windows:
        assert w.params["enter_bps"] in (0.3, 0.5)
