from __future__ import annotations

import pytest

from hft.backtest.costs import CostModel


def test_pip_value_per_lot():
    cm = CostModel()
    assert cm.pip_value_per_lot == pytest.approx(10.0)


def test_spread_prefers_bar_value():
    cm = CostModel(default_spread_pips=0.7)
    assert cm.spread(0.00012) == pytest.approx(0.00012)
    assert cm.spread(None) == pytest.approx(0.00007)
    assert cm.spread(0.0) == pytest.approx(0.00007)  # zero is not a real spread


def test_round_trip_cost():
    cm = CostModel(default_spread_pips=0.7, slippage_pips=0.2, commission_per_lot_side=3.5)
    # px cost = 0.7 + 2*0.2 = 1.1 pips = $11/lot; commission = $7/lot RT
    assert cm.round_trip_cost_usd(1.0) == pytest.approx(18.0)
    assert cm.round_trip_cost_usd(0.5) == pytest.approx(9.0)


def test_swap_signs_and_triple():
    cm = CostModel(swap_long_pips_per_day=-0.55, swap_short_pips_per_day=0.15)
    # one normal night, long, 1 lot: -0.55 pips * $10 = -$5.50
    assert cm.swap(+1, 1.0, [0]) == pytest.approx(-5.50)
    # Wed->Thu rollover (new-day weekday 3) carries the T+2 triple
    assert cm.swap(+1, 1.0, [3]) == pytest.approx(-16.50)
    # Tue->Wed rollover (new-day weekday 2) is a normal night
    assert cm.swap(+1, 1.0, [2]) == pytest.approx(-5.50)
    # short earns here
    assert cm.swap(-1, 1.0, [0]) == pytest.approx(1.50)
    # a full week of rollovers = 7 nights charged (5 charges, Thu tripled)
    assert cm.swap(+1, 1.0, [1, 2, 3, 4, 0]) == pytest.approx(-0.55 * 7 * 10)
