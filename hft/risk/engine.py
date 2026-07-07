"""Prop-firm risk engine — Python reference implementation.

The MQL5 include (mql5/Include/RiskEngine.mqh) mirrors this class method-for-method;
the parity gate diffs their decisions. Limits come from a per-firm config that is
frozen at deploy and excluded from any optimization loop (design doc, Compliance).

Semantics:
- daily loss limit: equity may not drop more than daily_loss_frac below the day
  anchor (max of balance/equity at day rollover — FTMO-style; confirm on pinning).
- total drawdown: equity may not drop more than total_drawdown_frac below the
  initial balance (static mode).
- A BREACH is a recorded violation and permanently halts trading (in the
  evaluation business, a breach is account death — the engine treats it that way).
- Before a breach ever happens, the engine BLOCKS new entries whose worst-case
  loss (stop distance times a safety factor, the factor sized to also absorb
  spread/slippage/commission) doesn't fit inside the remaining daily/total
  headroom. Blocking is normal operation; breaching is failure.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class FirmConfig:
    daily_loss_frac: float
    total_drawdown_frac: float
    max_lots: float
    risk_per_trade_frac: float
    daily_headroom_safety_factor: float = 2.0
    lot_step: float = 0.01
    min_lot: float = 0.01
    verified: bool = False

    @classmethod
    def from_json(cls, path: str | Path) -> "FirmConfig":
        raw = json.loads(Path(path).read_text())
        own = raw.get("own_policy", {})
        return cls(
            daily_loss_frac=raw["daily_loss_frac"],
            total_drawdown_frac=raw["total_drawdown_frac"],
            max_lots=raw["max_lots"],
            risk_per_trade_frac=own.get("risk_per_trade_frac", 0.005),
            daily_headroom_safety_factor=own.get("daily_headroom_safety_factor", 2.0),
            verified=bool(raw.get("verified", False)),
        )


@dataclass
class Violation:
    kind: str  # "daily_loss" | "total_drawdown"
    equity: float
    limit: float
    time: object = None


class RiskEngine:
    def __init__(self, config: FirmConfig, initial_balance: float, pip_value_per_lot: float = 10.0):
        self.cfg = config
        self.initial_balance = float(initial_balance)
        self.pip_value_per_lot = float(pip_value_per_lot)
        self.day_anchor = float(initial_balance)
        self.halted = False
        self.violations: list[Violation] = []

    # --- day lifecycle -----------------------------------------------------
    def on_day_start(self, balance: float, equity: float) -> None:
        """Called at every day rollover. FTMO-style anchor: max(balance, equity)."""
        self.day_anchor = max(float(balance), float(equity))

    # --- limits ------------------------------------------------------------
    @property
    def daily_loss_floor(self) -> float:
        return self.day_anchor - self.cfg.daily_loss_frac * self.initial_balance

    @property
    def total_drawdown_floor(self) -> float:
        return self.initial_balance * (1.0 - self.cfg.total_drawdown_frac)

    def on_mark(self, equity: float, time=None) -> bool:
        """Mark-to-market check. Returns True if a breach happened (engine halts)."""
        if self.halted:
            return False
        if equity <= self.daily_loss_floor:
            self.violations.append(Violation("daily_loss", equity, self.daily_loss_floor, time))
            self.halted = True
            return True
        if equity <= self.total_drawdown_floor:
            self.violations.append(
                Violation("total_drawdown", equity, self.total_drawdown_floor, time)
            )
            self.halted = True
            return True
        return False

    # --- sizing ------------------------------------------------------------
    def allowed_lots(self, stop_pips: float, equity: float) -> float:
        """Lots for a new entry, honoring per-trade risk, daily/total headroom
        (with safety factor), and the firm's lot cap. 0.0 means: do not trade."""
        # Note: cfg.verified gates DEMO/LIVE deployment (enforced by the EA and
        # deploy checklist), not backtests — research must run on placeholder
        # configs before the rulebook is pinned.
        if self.halted or stop_pips <= 0:
            return 0.0
        risk_usd = self.cfg.risk_per_trade_frac * equity
        lots = risk_usd / (stop_pips * self.pip_value_per_lot)

        headroom_daily = equity - self.daily_loss_floor
        headroom_total = equity - self.total_drawdown_floor
        headroom = min(headroom_daily, headroom_total)
        if headroom <= 0:
            return 0.0
        worst_case_per_lot = stop_pips * self.pip_value_per_lot * self.cfg.daily_headroom_safety_factor
        lots = min(lots, headroom / worst_case_per_lot)

        lots = min(lots, self.cfg.max_lots)
        lots = math.floor(lots / self.cfg.lot_step) * self.cfg.lot_step
        if lots < self.cfg.min_lot:
            return 0.0
        return round(lots, 2)
