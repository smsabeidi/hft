from __future__ import annotations

import pytest

from hft.backtest.montecarlo import ChallengeParams, ChallengeResult, simulate_challenge


def test_strong_edge_mostly_passes():
    # $30/trade on $60 std, 3 trades/day: ~$90/day on a $5k target
    res = simulate_challenge(30.0, 60.0, ChallengeParams(), n_sims=500, seed=1)
    assert res.p_pass > 0.9
    assert res.median_days_to_pass < 90


def test_negative_edge_never_passes():
    res = simulate_challenge(-20.0, 100.0, ChallengeParams(), n_sims=500, seed=2)
    assert res.p_pass < 0.02
    assert res.p_daily_breach + res.p_total_breach + res.p_timeout > 0.98


def test_zero_edge_is_a_coin_flip_paid_in_fees():
    # no edge: some sims luck into the target, most breach or stall —
    # the calculator must NOT flatter this case
    res = simulate_challenge(0.0, 150.0, ChallengeParams(), n_sims=500, seed=3)
    assert res.p_pass < 0.5
    assert res.expected_attempts_per_pass > 1.5


def test_deterministic_with_seed():
    a = simulate_challenge(10.0, 100.0, n_sims=300, seed=7)
    b = simulate_challenge(10.0, 100.0, n_sims=300, seed=7)
    assert a == b


def test_outcome_probabilities_sum_to_one():
    res = simulate_challenge(5.0, 120.0, n_sims=400, seed=4)
    total = res.p_pass + res.p_daily_breach + res.p_total_breach + res.p_timeout
    assert total == pytest.approx(1.0)


def test_rejects_bad_std():
    with pytest.raises(ValueError):
        simulate_challenge(10.0, 0.0)