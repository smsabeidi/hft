from __future__ import annotations

import pytest

from hft.risk.engine import FirmConfig, RiskEngine


def _engine(**overrides) -> RiskEngine:
    cfg = FirmConfig(
        daily_loss_frac=0.05,
        total_drawdown_frac=0.10,
        max_lots=5.0,
        risk_per_trade_frac=0.005,
        daily_headroom_safety_factor=2.0,
        **overrides,
    )
    return RiskEngine(cfg, initial_balance=50_000.0)


def test_floors():
    r = _engine()
    assert r.daily_loss_floor == pytest.approx(47_500.0)  # 50k anchor - 5% of 50k
    assert r.total_drawdown_floor == pytest.approx(45_000.0)


def test_daily_breach_halts():
    r = _engine()
    assert r.on_mark(47_400.0) is True
    assert r.halted
    assert r.violations[0].kind == "daily_loss"
    # once halted, no more violations pile up and no sizing
    assert r.on_mark(40_000.0) is False
    assert r.allowed_lots(10.0, 47_400.0) == 0.0


def test_total_drawdown_breach_after_good_days():
    r = _engine()
    # profits raised the day anchor; daily floor now above total floor
    r.on_day_start(balance=45_600.0, equity=45_600.0)
    assert r.daily_loss_floor == pytest.approx(43_100.0)
    assert r.on_mark(44_950.0) is True  # breaches total (45k) before daily (43.1k)
    assert r.violations[0].kind == "total_drawdown"


def test_day_anchor_uses_max_of_balance_equity():
    r = _engine()
    r.on_day_start(balance=50_000.0, equity=51_200.0)
    assert r.day_anchor == pytest.approx(51_200.0)
    assert r.daily_loss_floor == pytest.approx(51_200.0 - 2_500.0)


def test_sizing_basic():
    r = _engine()
    # 0.5% of 50k = $250 risk; 10-pip stop @ $10/pip/lot -> 2.5 lots
    assert r.allowed_lots(10.0, 50_000.0) == pytest.approx(2.5)


def test_sizing_respects_max_lots():
    r = _engine()
    # 2-pip stop -> raw 12.5 lots -> capped at 5
    assert r.allowed_lots(2.0, 50_000.0) == pytest.approx(5.0)


def test_sizing_respects_daily_headroom():
    r = _engine()
    # equity already close to the daily floor: headroom $100
    equity = 47_600.0
    lots = r.allowed_lots(10.0, equity)
    # worst case per lot = 10 pips * $10 * safety 2.0 = $200 -> 0.5 lots max
    assert lots <= 0.5
    assert lots > 0


def test_sizing_zero_when_no_headroom_or_bad_stop():
    r = _engine()
    assert r.allowed_lots(10.0, 47_500.0) == 0.0  # at the floor
    assert r.allowed_lots(0.0, 50_000.0) == 0.0
    assert r.allowed_lots(-5.0, 50_000.0) == 0.0


def test_sizing_lot_rounding():
    r = _engine()
    # 0.5% of 1000 = $5 risk; 10-pip stop -> 0.05 lots
    r2 = RiskEngine(r.cfg, initial_balance=1_000.0)
    assert r2.allowed_lots(10.0, 1_000.0) == pytest.approx(0.05)
    # tiny equity -> below min lot -> 0
    r3 = RiskEngine(r.cfg, initial_balance=100.0)
    assert r3.allowed_lots(10.0, 100.0) == 0.0
