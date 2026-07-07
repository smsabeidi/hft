from __future__ import annotations

import pytest

from hft.crypto.paper_funding import PaperFundingEngine, PaperParams


class FakeOKX:
    """Injectable stand-in for the live endpoints. Rates are (funding_ts_ms, rate)."""

    def __init__(self, bid: float = 100.0, ask: float = 100.02):
        self.rates: list[tuple[int, float]] = []
        self.bid, self.ask = bid, ask
        # per-instrument 1m candle closes: {inst: {minute_ts_ms: close}}
        self.closes: dict[str, dict[int, float]] = {}
        self.candles_raise = False

    def add_funding(self, ts_ms: int, rate: float) -> None:
        self.rates.append((ts_ms, rate))

    def funding_history(self, inst: str, limit: int = 20) -> list[dict]:
        newest_first = sorted(self.rates, reverse=True)[:limit]
        return [
            {"fundingTime": str(ts), "realizedRate": str(r)} for ts, r in newest_first
        ]

    def ticker(self, inst: str) -> dict:
        return {"bidPx": str(self.bid), "askPx": str(self.ask)}

    def candles_1m(self, inst: str, after_ms: int, limit: int = 100) -> list[list[str]]:
        if self.candles_raise:
            raise RuntimeError("candle endpoint down")
        return [
            [str(ts), "0", "0", "0", str(close)]
            for ts, close in sorted(self.closes.get(inst, {}).items(), reverse=True)
            if ts < after_ms
        ][:limit]


PARAMS = PaperParams(smooth_n=3, enter_bps=0.5, exit_bps=0.0, fee_rt_bps=25.0, utilization=0.6)

# cost arithmetic for the fake book: half the RT fee plus the doubled observed
# half-spread, both scaled by utilization
FEE_HALF = (25.0 / 1e4) / 2 * 0.6
HALF_SPREAD = (100.02 - 100.0) / 2 / 100.01
SPREAD_COST = 2 * HALF_SPREAD * 0.6
ENTRY_COST = FEE_HALF + SPREAD_COST


def _engine(tmp_path, api):
    return PaperFundingEngine(PARAMS, tmp_path / "state.json", api=api)


def test_warmup_until_enough_rates(tmp_path):
    api = FakeOKX()
    api.add_funding(1_000, 1e-4)
    api.add_funding(2_000, 1e-4)
    eng = _engine(tmp_path, api)
    assert eng.tick(now_ms=10_000)["action"] == "warmup"
    assert eng.state["on"] is False


def test_enter_charges_fee_and_observed_spread(tmp_path):
    api = FakeOKX()
    for i, ts in enumerate((1_000, 2_000, 3_000)):
        api.add_funding(ts, 1e-4)  # smooth = 1bp > 0.5bp threshold
    eng = _engine(tmp_path, api)
    out = eng.tick(now_ms=10_000)
    assert out["action"].startswith("ENTER")
    assert eng.state["on"] is True
    assert eng.state["last_funding_ts"] == 3_000  # trigger event not accrued
    assert eng.state["equity"] == pytest.approx(-ENTRY_COST)
    assert eng.state["episode_costs"] == pytest.approx(ENTRY_COST)


def test_accrues_only_new_funding_events_once(tmp_path):
    api = FakeOKX()
    for ts in (1_000, 2_000, 3_000):
        api.add_funding(ts, 1e-4)
    eng = _engine(tmp_path, api)
    eng.tick(now_ms=10_000)  # enter
    api.add_funding(4_000, 2e-4)  # one new event while on
    out = eng.tick(now_ms=20_000)
    assert "accrued 1" in out["action"]
    assert eng.state["episode_gross"] == pytest.approx(2e-4 * 0.6)
    assert eng.state["equity"] == pytest.approx(-ENTRY_COST + 2e-4 * 0.6)
    # same history again: idempotent, nothing double-accrued
    out2 = eng.tick(now_ms=30_000)
    assert out2["action"] == "hold"
    assert eng.state["equity"] == pytest.approx(-ENTRY_COST + 2e-4 * 0.6)


def test_exit_records_episode_net(tmp_path):
    api = FakeOKX()
    for ts in (1_000, 2_000, 3_000):
        api.add_funding(ts, 1e-4)
    eng = _engine(tmp_path, api)
    eng.tick(now_ms=10_000)  # enter
    api.add_funding(4_000, 2e-4)
    eng.tick(now_ms=20_000)  # accrue
    # three strongly negative rates drive the smooth below the exit threshold
    for ts in (5_000, 6_000, 7_000):
        api.add_funding(ts, -2e-4)
    out = eng.tick(now_ms=40_000)
    assert out["action"].startswith("EXIT")
    assert eng.state["on"] is False
    assert len(eng.state["episodes"]) == 1
    ep = eng.state["episodes"][0]
    # gross includes every event accrued while on (2e-4 then the negatives)
    expected_gross = (2e-4 - 2e-4 - 2e-4 - 2e-4) * 0.6
    assert ep["gross"] == pytest.approx(expected_gross)
    assert ep["costs"] == pytest.approx(2 * ENTRY_COST)
    assert ep["net"] == pytest.approx(expected_gross - 2 * ENTRY_COST)
    # equity is consistent with the episode record
    assert eng.state["equity"] == pytest.approx(ep["net"])


def test_catches_up_after_missed_ticks(tmp_path):
    """A sleeping laptop misses cron runs; the next tick must accrue EVERY
    funding event since the last one it saw, not just the newest."""
    api = FakeOKX()
    for ts in (1_000, 2_000, 3_000):
        api.add_funding(ts, 1e-4)
    eng = _engine(tmp_path, api)
    eng.tick(now_ms=10_000)  # enter, last_funding_ts=3000
    # five funding events land while the laptop was asleep
    for ts in (4_000, 5_000, 6_000, 7_000, 8_000):
        api.add_funding(ts, 1e-4)
    out = eng.tick(now_ms=50_000)
    assert "accrued 5" in out["action"]
    assert eng.state["episode_gross"] == pytest.approx(5 * 1e-4 * 0.6)
    assert eng.state["last_funding_ts"] == 8_000


def test_hysteresis_no_entry_between_thresholds(tmp_path):
    api = FakeOKX()
    for ts in (1_000, 2_000, 3_000):
        api.add_funding(ts, 0.3e-4)  # 0.3bp: above exit (0), below enter (0.5)
    eng = _engine(tmp_path, api)
    out = eng.tick(now_ms=10_000)
    assert out["action"] == "hold"
    assert eng.state["on"] is False


def test_state_survives_restart(tmp_path):
    api = FakeOKX()
    for ts in (1_000, 2_000, 3_000):
        api.add_funding(ts, 1e-4)
    eng = _engine(tmp_path, api)
    eng.tick(now_ms=10_000)
    # new engine instance on the same state file = cron re-invocation
    eng2 = _engine(tmp_path, api)
    assert eng2.state["on"] is True
    assert eng2.state["equity"] == pytest.approx(-ENTRY_COST)
    assert eng2.state["last_funding_ts"] == 3_000


def _entered_engine(tmp_path, api, now_ms: int):
    """Engine that has just ENTERed at now_ms (smooth = 1bp > threshold)."""
    for ts in (1_000, 2_000, 3_000):
        api.add_funding(ts, 1e-4)
    eng = _engine(tmp_path, api)
    out = eng.tick(now_ms=now_ms)
    assert out["action"].startswith("ENTER")
    return eng


def test_enter_records_pending_fill_with_basis(tmp_path):
    api = FakeOKX()
    eng = _entered_engine(tmp_path, api, now_ms=600_000)
    assert len(eng.state["pending_fills"]) == 1
    fill = eng.state["pending_fills"][0]
    assert fill["kind"] == "enter"
    # perp and spot tickers are identical in the fake, so basis == 0
    assert fill["basis"] == pytest.approx(0.0)
    assert eng.state["markouts"] == []


def test_markouts_resolved_after_horizon(tmp_path):
    api = FakeOKX()
    eng = _entered_engine(tmp_path, api, now_ms=600_000)  # fill at t=10min
    # perp trades 1% below spot at every later minute: basis fell after an
    # entry (which sells the perp leg) -> favorable -> +100bps markout
    minutes = [600_000 + m * 60_000 for m in (1, 5, 15, 60)]
    api.closes["BTC-USDT-SWAP"] = {ts: 99.0 for ts in minutes}
    api.closes["BTC-USDT"] = {ts: 100.0 for ts in minutes}
    out = eng.tick(now_ms=600_000 + 63 * 60_000)
    assert eng.state["pending_fills"] == []
    assert len(eng.state["markouts"]) == 1
    mk = eng.state["markouts"][0]
    assert mk["kind"] == "enter"
    for m in (1, 5, 15, 60):
        assert mk[f"m{m}"] == pytest.approx(100.0, abs=0.01)


def test_markout_failure_is_retried_not_fatal(tmp_path):
    api = FakeOKX()
    eng = _entered_engine(tmp_path, api, now_ms=600_000)
    api.candles_raise = True
    out = eng.tick(now_ms=600_000 + 63 * 60_000)  # tick itself must not fail
    assert out["on"] is True
    assert len(eng.state["pending_fills"]) == 1
    assert eng.state["pending_fills"][0]["tries"] == 1
    # endpoint recovers: next tick resolves the markout
    api.candles_raise = False
    minutes = [600_000 + m * 60_000 for m in (1, 5, 15, 60)]
    api.closes["BTC-USDT-SWAP"] = {ts: 100.0 for ts in minutes}
    api.closes["BTC-USDT"] = {ts: 100.0 for ts in minutes}
    eng.tick(now_ms=600_000 + 64 * 60_000)
    assert eng.state["pending_fills"] == []
    assert len(eng.state["markouts"]) == 1
    assert eng.state["markouts"][0]["m5"] == pytest.approx(0.0, abs=0.01)


def test_old_state_files_gain_markout_keys(tmp_path):
    """State files written before markout tracking must load cleanly."""
    api = FakeOKX()
    eng = _entered_engine(tmp_path, api, now_ms=600_000)
    state = eng.state_path.read_text()
    import json

    s = json.loads(state)
    del s["pending_fills"], s["markouts"]
    eng.state_path.write_text(json.dumps(s))
    eng2 = _engine(tmp_path, api)
    assert eng2.state["pending_fills"] == []
    assert eng2.state["markouts"] == []


def test_log_is_capped(tmp_path):
    api = FakeOKX()
    for ts in (1_000, 2_000, 3_000):
        api.add_funding(ts, 0.3e-4)
    eng = _engine(tmp_path, api)
    for k in range(520):
        eng.tick(now_ms=10_000 + k)
    assert len(eng.state["log"]) == 500
