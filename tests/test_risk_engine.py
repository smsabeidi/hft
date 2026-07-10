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


# --- equity-curve throttle (anti-martingale), adopted 2026-07-09 ------------

def test_throttle_full_size_below_5pct_dd():
    r = _engine()
    assert r.throttle_multiplier(50_000.0) == 1.00
    assert r.throttle_multiplier(48_000.0) == 1.00   # 4% dd


def test_throttle_tiers_and_standdown():
    r = _engine()
    r.on_mark(50_000.0)                              # establish peak
    assert r.throttle_multiplier(47_000.0) == 0.60   # 6% dd
    assert r.throttle_multiplier(45_500.0) == 0.35   # 9% dd
    assert r.throttle_multiplier(43_900.0) == 0.00   # 12.2% dd -> stand down
    # NOTE: dd >= 12% only occurs pre-breach here because this config's
    # total-drawdown floor (10%) would normally halt first; the tier exists
    # for firms/configs with wider total limits.


def test_throttle_scales_allowed_lots():
    r = _engine()
    full = r.allowed_lots(10.0, 50_000.0)
    r.peak_equity = 50_000.0
    # roll the day so daily headroom exists at the drawn-down equity —
    # otherwise the (correct) headroom block fires before the throttle
    r.on_day_start(balance=47_000.0, equity=47_000.0)
    throttled = r.allowed_lots(10.0, 47_000.0)       # 6% dd from peak -> 0.60x
    assert throttled == pytest.approx(0.60 * full * (47_000.0 / 50_000.0), abs=0.02)


def test_headroom_block_precedes_throttle_intraday():
    """At 6% intraday drawdown under a 5% daily limit, the daily-headroom
    block (not the throttle) is what stops new risk — layered defense."""
    r = _engine()
    r.on_mark(50_000.0)
    assert r.allowed_lots(10.0, 47_000.0) == 0.0


def test_throttle_restores_at_new_high():
    r = _engine()
    r.on_mark(50_000.0)
    assert r.throttle_multiplier(47_000.0) == 0.60
    assert r.throttle_multiplier(50_500.0) == 1.00   # new high advances peak
    assert r.peak_equity == pytest.approx(50_500.0)
    assert r.throttle_multiplier(49_000.0) == 1.00   # 2.97% dd from new peak


def test_peak_never_decreases():
    r = _engine()
    r.on_mark(52_000.0)
    r.on_mark(48_000.0)
    assert r.peak_equity == pytest.approx(52_000.0)
