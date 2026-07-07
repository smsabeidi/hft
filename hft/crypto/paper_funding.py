"""Paper-trading engine for the funding-capture family — its NEXT GATE.

The strategy passed round 1 (walk-forward on 5.5y of real funding history).
The gate after that is a live paper implementation: same hysteresis state
machine, but decisions run against the LIVE venue (OKX public endpoints) and
fills are simulated at live top-of-book with the fee model. State persists in
a JSON file, so the engine is cron-able: run `--once` every few minutes and it
picks up where it left off — laptop-grade ops now, VM-grade later.

Accounting (fraction of nominal capital, same conventions as the backtest):
- entry/exit: half the round-trip fee each, plus the OBSERVED half-spread on
  both legs (live books make the spread cost real, not modeled)
- while on: accrue funding_rate x utilization at each new funding event
- promotion criterion (design doc demo-gate spirit): >=10 live paper episodes
  with accounting consistent with the backtest's assumptions before any real
  capital conversation.

This engine trades NOTHING. It writes numbers to a JSON file.
"""

from __future__ import annotations

import json
import ssl
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

OKX_REST = "https://www.okx.com"

# Markout horizons (minutes). Markout = basis drift after a fill, signed so
# positive = favorable. This is how market makers measure adverse selection;
# here it detects entering/exiting the basis position exactly when the basis
# is about to move against the book — toxicity that episode-level P&L hides.
MARKOUT_HORIZONS_MIN = (1, 5, 15, 60)
_MARKOUT_SETTLE_MS = (MARKOUT_HORIZONS_MIN[-1] + 2) * 60_000
_MARKOUT_MAX_TRIES = 20  # give up on a fill's markouts after this many failed fetches


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _get_json(path: str) -> dict:
    req = urllib.request.Request(OKX_REST + path, headers={"User-Agent": "hft-harness/0.1"})
    with urllib.request.urlopen(req, timeout=20, context=_ssl_context()) as r:
        return json.loads(r.read())


@dataclass(frozen=True)
class PaperParams:
    perp_inst: str = "BTC-USDT-SWAP"
    enter_bps: float = 0.5
    exit_bps: float = 0.0
    smooth_n: int = 9
    fee_rt_bps: float = 25.0
    utilization: float = 0.6


class OKXPublic:
    """Thin fetch layer, injectable for tests."""

    def funding_history(self, inst: str, limit: int = 20) -> list[dict]:
        data = _get_json(f"/api/v5/public/funding-rate-history?instId={inst}&limit={limit}")
        return data.get("data", [])

    def ticker(self, inst: str) -> dict:
        data = _get_json(f"/api/v5/market/ticker?instId={inst}")
        return data["data"][0]

    def candles_1m(self, inst: str, after_ms: int, limit: int = 100) -> list[list[str]]:
        """1m candles strictly older than after_ms, newest first (OKX 'after'
        is a pagination cursor, not a range start)."""
        data = _get_json(
            f"/api/v5/market/history-candles?instId={inst}&bar=1m&after={after_ms}&limit={limit}"
        )
        return data.get("data", [])


class PaperFundingEngine:
    def __init__(self, params: PaperParams, state_path: Path, api: OKXPublic | None = None):
        self.p = params
        self.state_path = Path(state_path)
        self.api = api or OKXPublic()
        self.state = self._load()

    def _load(self) -> dict:
        defaults = {
            "on": False,
            "equity": 0.0,  # cumulative return, fraction of capital
            "entry_time": None,
            "episode_gross": 0.0,
            "episode_costs": 0.0,
            "last_funding_ts": 0,
            "episodes": [],
            "log": [],
            "pending_fills": [],  # fills awaiting markout computation
            "markouts": [],       # completed markout records (diagnostic only)
        }
        if self.state_path.exists():
            state = json.loads(self.state_path.read_text())
            for key, value in defaults.items():
                state.setdefault(key, value)
            return state
        return defaults

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.state, indent=1))

    @property
    def spot_inst(self) -> str:
        return self.p.perp_inst.removesuffix("-SWAP")

    def _basis_now(self) -> float | None:
        """Perp-vs-spot basis at the ticker mids, as a fraction. None on any
        fetch failure — markouts are diagnostics and must never break a tick."""
        try:
            perp = self.api.ticker(self.p.perp_inst)
            spot = self.api.ticker(self.spot_inst)
            perp_mid = (float(perp["bidPx"]) + float(perp["askPx"])) / 2
            spot_mid = (float(spot["bidPx"]) + float(spot["askPx"])) / 2
            return perp_mid / spot_mid - 1
        except Exception:
            return None

    def _record_fill(self, ts_ms: int, kind: str) -> None:
        basis = self._basis_now()
        if basis is None:
            return  # no baseline captured: this fill simply has no markouts
        self.state["pending_fills"].append({"ts": ts_ms, "kind": kind, "basis": basis, "tries": 0})

    def _markouts_for(self, fill: dict) -> dict:
        after = fill["ts"] + MARKOUT_HORIZONS_MIN[-1] * 60_000 + 120_000
        perp = {int(c[0]): float(c[4]) for c in self.api.candles_1m(self.p.perp_inst, after)}
        spot = {int(c[0]): float(c[4]) for c in self.api.candles_1m(self.spot_inst, after)}
        # enter sells the perp leg: a falling basis afterwards is favorable.
        # exit buys it back: a rising basis afterwards is favorable.
        direction = -1.0 if fill["kind"] == "enter" else 1.0
        out: dict = {}
        for m in MARKOUT_HORIZONS_MIN:
            minute = (fill["ts"] + m * 60_000) // 60_000 * 60_000
            if minute not in perp or minute not in spot:
                out[f"m{m}"] = None
                continue
            basis_h = perp[minute] / spot[minute] - 1
            out[f"m{m}"] = round(direction * (basis_h - fill["basis"]) * 1e4, 4)
        if all(v is None for v in out.values()):
            raise RuntimeError("no overlapping 1m candles for markout window")
        return out

    def _process_markouts(self, now_ms: int) -> None:
        """Resolve markouts for fills whose longest horizon has elapsed.
        Failures are retried on later ticks up to _MARKOUT_MAX_TRIES.
        Diagnostic only — never touches equity or the promotion gate."""
        ready = [f for f in self.state["pending_fills"] if now_ms >= f["ts"] + _MARKOUT_SETTLE_MS]
        for fill in ready:
            try:
                marks = self._markouts_for(fill)
            except Exception:
                fill["tries"] = fill.get("tries", 0) + 1
                if fill["tries"] >= _MARKOUT_MAX_TRIES:
                    self.state["pending_fills"].remove(fill)
                continue
            self.state["pending_fills"].remove(fill)
            self.state["markouts"].append(
                {
                    "ts": fill["ts"],
                    "kind": fill["kind"],
                    "basis_bps": round(fill["basis"] * 1e4, 4),
                    **marks,
                }
            )
            self.state["markouts"] = self.state["markouts"][-500:]

    def _spread_cost(self) -> float:
        """Observed half-spread on the perp leg (fraction of price), doubled
        as a proxy for the spot leg too — measured, not assumed."""
        t = self.api.ticker(self.p.perp_inst)
        bid, ask = float(t["bidPx"]), float(t["askPx"])
        mid = (bid + ask) / 2
        half_spread = (ask - bid) / 2 / mid
        return 2 * half_spread * self.p.utilization

    def tick(self, now_ms: int | None = None) -> dict:
        """One evaluation. Cron-able; idempotent between funding events."""
        now_ms = now_ms or int(time.time() * 1000)
        # catch-up window: 30 events = 10 days of 8h funding. A sleeping
        # laptop that misses cron ticks self-heals on the next run as long as
        # the gap is inside this window; beyond it, accrued gross would be
        # silently understated (OKX caps the endpoint at 100).
        hist = self.api.funding_history(self.p.perp_inst, limit=max(self.p.smooth_n, 30))
        # OKX returns newest first; realized rates only
        rates = [float(h["realizedRate"]) for h in hist if h.get("realizedRate")]
        if len(rates) < self.p.smooth_n:
            return {"action": "warmup", "on": self.state["on"]}
        smooth = sum(rates[: self.p.smooth_n]) / self.p.smooth_n
        newest_ts = int(hist[0]["fundingTime"])
        fee_half = (self.p.fee_rt_bps / 1e4) / 2 * self.p.utilization

        action = "hold"
        # accrue funding events that happened while on
        if self.state["on"] and newest_ts > self.state["last_funding_ts"]:
            new = [
                float(h["realizedRate"])
                for h in hist
                if int(h["fundingTime"]) > self.state["last_funding_ts"] and h.get("realizedRate")
            ]
            accrual = sum(new) * self.p.utilization
            self.state["episode_gross"] += accrual
            self.state["equity"] += accrual
            self.state["last_funding_ts"] = newest_ts
            action = f"accrued {len(new)} funding event(s)"

        if not self.state["on"] and smooth > self.p.enter_bps / 1e4:
            cost = fee_half + self._spread_cost()
            self.state.update(
                on=True,
                entry_time=now_ms,
                episode_gross=0.0,
                episode_costs=cost,
                last_funding_ts=newest_ts,
            )
            self.state["equity"] -= cost
            self._record_fill(now_ms, "enter")
            action = f"ENTER (smooth={smooth * 1e4:.2f}bps, cost={cost * 1e4:.1f}bps)"
        elif self.state["on"] and smooth < self.p.exit_bps / 1e4:
            cost = fee_half + self._spread_cost()
            self.state["equity"] -= cost
            total_costs = self.state.get("episode_costs", 0.0) + cost
            gross = self.state["episode_gross"]
            self.state["episodes"].append(
                {
                    "entry_time": self.state["entry_time"],
                    "exit_time": now_ms,
                    "gross": gross,
                    "costs": total_costs,
                    # net is what the promotion criterion compares against the
                    # backtest's mean episode net (74.2 bps in round 1)
                    "net": gross - total_costs,
                }
            )
            self.state.update(on=False, entry_time=None, episode_gross=0.0, episode_costs=0.0)
            self._record_fill(now_ms, "exit")
            action = f"EXIT (smooth={smooth * 1e4:.2f}bps, cost={cost * 1e4:.1f}bps)"

        self._process_markouts(now_ms)

        entry = {
            "ts": now_ms,
            "action": action,
            "on": self.state["on"],
            "smooth_bps": round(smooth * 1e4, 3),
            "equity_bps": round(self.state["equity"] * 1e4, 2),
        }
        self.state["log"].append(entry)
        self.state["log"] = self.state["log"][-500:]
        self._save()
        return entry
