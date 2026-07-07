"""C5 machinery tests — SYNTHETIC data only, per the blind-build rule in
reports/m3_preregistration.md. No recorded market data is read here."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hft.crypto.basis_meanrev import (
    C5Params,
    build_basis_frame,
    run_c5,
    zscore,
)


def _books(ts_ms, mids, half_spread=0.5):
    """Synthetic books5 frame: mid +/- half_spread (absolute px units)."""
    mids = np.asarray(mids, dtype=float)
    return pd.DataFrame(
        {
            "ts": np.asarray(ts_ms, dtype="int64"),
            "bid1_px": mids - half_spread,
            "ask1_px": mids + half_spread,
        }
    )


def _frame_from_basis(basis_path, spot_px=10_000.0, seconds_step=5):
    """Perp/spot pair whose mid-basis follows basis_path exactly."""
    n = len(basis_path)
    ts = (np.arange(n) * seconds_step * 1000).astype("int64")
    spot = _books(ts, np.full(n, spot_px), half_spread=0.5)
    perp = _books(ts, spot_px * (1 + np.asarray(basis_path)), half_spread=0.5)
    return build_basis_frame(perp, spot)


def test_build_basis_frame_matches_and_measures_spread():
    ts = np.array([0, 5_000, 10_000], dtype="int64")
    spot = _books(ts, [10_000.0] * 3, half_spread=1.0)
    perp = _books(ts + 200, [10_010.0] * 3, half_spread=2.0)  # +200ms, inside tolerance
    frame = build_basis_frame(perp, spot)
    assert len(frame) == 3
    assert frame["basis"].iloc[0] == pytest.approx(0.001, rel=1e-6)
    assert frame["hs_spot"].iloc[0] == pytest.approx(1.0 / 10_000, rel=1e-3)
    assert frame["hs_perp"].iloc[0] == pytest.approx(2.0 / 10_010, rel=1e-3)


def test_unmatched_snapshots_are_dropped():
    spot = _books(np.array([0, 5_000], dtype="int64"), [10_000.0] * 2)
    perp = _books(np.array([0, 5_900], dtype="int64"), [10_000.0] * 2)  # 900ms > tolerance
    frame = build_basis_frame(perp, spot)
    assert len(frame) == 1


def test_zscore_is_causal():
    """z at time t must not change when only FUTURE values change."""
    rng = np.random.default_rng(7)
    base = rng.normal(0, 1e-4, 400)
    a = pd.Series(base.copy())
    b = pd.Series(base.copy())
    b.iloc[300:] += 5e-3  # rewrite the future
    za = zscore(a, w_min=10)
    zb = zscore(b, w_min=10)
    pd.testing.assert_series_equal(za.iloc[:300], zb.iloc[:300])


def test_one_episode_on_spike_and_reversion():
    # flat basis, a sustained positive spike, then reversion to flat
    path = [0.0] * 500 + [0.004] * 40 + [0.0] * 100
    frame = _frame_from_basis(path)
    trades = [t for t in run_c5(frame, C5Params(w_min=30, z_enter=2.0, z_exit=0.0)) if not t.shadow]
    assert len(trades) == 1
    tr = trades[0]
    assert tr.gross > 0  # entered high, exited near flat
    # net = gross - 25bp fees - four measured half-spreads (~0.005% each x4)
    assert tr.net == pytest.approx(tr.gross - 25e-4 - 4 * 0.5 / 10_000, abs=2e-5)


def test_negative_side_is_shadow_only():
    path = [0.0] * 500 + [-0.004] * 40 + [0.0] * 100
    frame = _frame_from_basis(path)
    trades = run_c5(frame, C5Params(w_min=30, z_enter=2.0, z_exit=0.0))
    real = [t for t in trades if not t.shadow]
    shadow = [t for t in trades if t.shadow]
    assert real == []
    assert len(shadow) == 1
    assert shadow[0].gross > 0  # the mirrored capture is recorded, not gated


def test_max_hold_forces_exit():
    # spike that never reverts: max_hold must close the trade
    path = [0.0] * 500 + [0.004] * 800
    frame = _frame_from_basis(path)
    trades = [
        t
        for t in run_c5(frame, C5Params(w_min=30, z_enter=2.0, z_exit=0.0, max_hold_min=10))
        if not t.shadow
    ]
    assert trades, "max_hold exit expected"
    held_s = (trades[0].exit_time - trades[0].entry_time).total_seconds()
    assert held_s <= 10 * 60 + 5


def test_flat_random_walk_loses_after_costs():
    """Falsification-style check: with no mean-reversion structure, costs
    must make expectancy negative — if this machine can't lose on noise,
    it can't be trusted to win on signal."""
    rng = np.random.default_rng(11)
    path = np.cumsum(rng.normal(0, 2e-5, 6_000))
    frame = _frame_from_basis(path)
    trades = [t for t in run_c5(frame, C5Params(w_min=30, z_enter=1.5, z_exit=0.0)) if not t.shadow]
    if trades:  # noise may trigger few trades; when it does, costs dominate
        assert sum(t.net for t in trades) < 0
