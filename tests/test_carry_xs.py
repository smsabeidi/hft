"""fx_carry_xs machinery — synthetic tests before the round runs."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hft.strategies.carry_xs import XSParams, _weights_for_day, run_xs


def _panel(n=300, ccys=("AAA", "BBB", "CCC"), diffs=(2.0, 0.0, -2.0),
           rets=None, vols=1.0, seed=0):
    idx = pd.date_range("2023-01-02", periods=n, freq="B")
    rng = np.random.default_rng(seed)
    out = pd.DataFrame(index=idx)
    for i, c in enumerate(ccys):
        r = rets[i] if rets is not None else rng.normal(0, 0.0, n)
        out[f"ret_{c}"] = r
        out[f"diff_{c}"] = diffs[i]
        out[f"vol_{c}"] = vols
    return out


def test_ranking_longs_top_shorts_bottom():
    p = _panel()
    w = _weights_for_day(p.iloc[0], ["AAA", "BBB", "CCC"], XSParams(k=1))
    assert w == {"AAA": 1.0, "CCC": -1.0}


def test_too_few_rankable_means_flat():
    p = _panel()
    p.loc[:, "diff_BBB"] = np.nan
    p.loc[:, "diff_CCC"] = np.nan
    w = _weights_for_day(p.iloc[0], ["AAA", "BBB", "CCC"], XSParams(k=1))
    assert w == {}


def test_carry_accrual_and_markup_on_gross():
    # zero price moves: pnl = carry spread minus markup on gross minus one entry cost
    p = _panel(n=260)
    daily = run_xs(p, XSParams(k=1, markup_pct=1.0))
    # long AAA (+2%), short CCC (-2%): carry spread 4%/yr; markup 1% x gross 2 = 2%/yr
    expected = (0.04 - 0.02)  # per year, fractions
    assert daily.sum() == pytest.approx(expected * len(p) / 252, abs=3e-3)


def test_weights_apply_next_day_not_rebalance_day():
    """Causality: the first Friday's chosen weights must not earn that
    Friday's return."""
    rets = [np.zeros(300), np.zeros(300), np.zeros(300)]
    rets[0][:6] = 0.01  # AAA rallies early in week 1
    p = _panel(rets=rets)
    daily = run_xs(p, XSParams(k=1, markup_pct=0.0))
    fri0 = np.where(p.index.dayofweek == 4)[0][0]
    assert (daily.iloc[: fri0 + 1] == 0).all()  # nothing held before/on first Friday


def test_turnover_cost_charged_on_change_only():
    p = _panel(n=30)
    daily = run_xs(p, XSParams(k=1, markup_pct=0.0))
    fri0 = np.where(p.index.dayofweek == 4)[0][0]
    # first application day: pays 2 units of turnover x 0.85bp AND earns
    # that day's carry (weights are live from the open of that day)
    assert daily.iloc[fri0 + 1] == pytest.approx(-2 * 0.85e-4 + 0.04 / 252, abs=1e-9)
    # steady state: same ranks -> no turnover -> carry only
    assert daily.iloc[fri0 + 3] == pytest.approx(0.04 / 252, abs=1e-9)


def test_inverse_vol_weights_tilt_to_quiet_leg():
    p = _panel(ccys=("AAA", "BBB", "CCC", "DDD"), diffs=(3.0, 2.0, -2.0, -3.0))
    p.loc[:, "vol_AAA"] = 0.05
    p.loc[:, "vol_BBB"] = 0.20
    w = _weights_for_day(p.iloc[0], ["AAA", "BBB", "CCC", "DDD"], XSParams(k=2, inv_vol=True))
    assert w["AAA"] > w["BBB"] > 0
    assert w["AAA"] + w["BBB"] == pytest.approx(1.0)
