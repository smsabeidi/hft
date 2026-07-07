"""Time-series momentum (TSMOM). CANDIDATE FAMILY #3, not a validated edge.

Hypothesis (a-priori, from the literature — Moskowitz/Ooi/Pedersen 2012, the
most documented trend anomaly in futures/FX): the sign of an instrument's own
past L-day return predicts its next-period return. Distinct from the two dead
families: horizon is days-to-weeks (latency-irrelevant), signal is trend
persistence (not range breakout, not reversion).

Rules:
- Once per completed UTC day: momentum = daily_close[-1] - daily_close[-1-L].
  Target side = sign(momentum).
- Enter (any bar, once flat) in the target direction with SL = k_atr x ATR(14d)
  in pips (clamped), TP far (exits happen via signal flips, not targets).
- If the target flips while holding, close; re-entry follows once flat.

Costs at this horizon: spread is negligible; SWAP dominates (weeks of
rollovers, Wednesday triple) — the engine charges it, which is exactly why
this family must earn its round honestly.
"""

from __future__ import annotations

from collections import deque

from hft.backtest.engine import Context
from hft.strategies.base import BaseStrategy


class TSMOM(BaseStrategy):
    param_grid = {
        "lookback_days": [20, 60],
        "k_atr": [2.0, 3.0],
    }

    def __init__(
        self,
        lookback_days: int = 60,
        k_atr: float = 3.0,
        atr_days: int = 14,
        min_sl_pips: float = 30.0,
        max_sl_pips: float = 400.0,
        pip_size: float = 0.0001,
    ):
        self.lookback_days = lookback_days
        self.k_atr = k_atr
        self.atr_days = atr_days
        self.min_sl_pips = min_sl_pips
        self.max_sl_pips = max_sl_pips
        self.pip_size = pip_size

        self._day = None
        self._day_high: float | None = None
        self._day_low: float | None = None
        self._day_close: float | None = None
        self._daily_closes: deque = deque(maxlen=lookback_days + 2)
        self._trs: deque = deque(maxlen=atr_days)
        self._target: int | None = None
        self._sl_pips: float | None = None

    def _finalize_day(self) -> None:
        """Roll the completed day into daily state and refresh the signal."""
        if self._day_close is None:
            return
        if self._daily_closes:
            prev_close = self._daily_closes[-1]
            tr = max(
                self._day_high - self._day_low,
                abs(self._day_high - prev_close),
                abs(self._day_low - prev_close),
            )
            self._trs.append(tr)
        self._daily_closes.append(self._day_close)

        if len(self._daily_closes) > self.lookback_days and len(self._trs) >= self.atr_days:
            momentum = self._daily_closes[-1] - self._daily_closes[-1 - self.lookback_days]
            self._target = 1 if momentum > 0 else -1
            atr_pips = (sum(self._trs) / len(self._trs)) / self.pip_size
            self._sl_pips = min(max(self.k_atr * atr_pips, self.min_sl_pips), self.max_sl_pips)

    def on_bar(self, ctx: Context) -> None:
        d = ctx.time.date()
        if self._day is None:
            self._day = d
        elif d != self._day:
            self._finalize_day()
            self._day = d
            self._day_high = self._day_low = self._day_close = None

        hi, lo, cl = ctx.high, ctx.low, ctx.close
        self._day_high = hi if self._day_high is None else max(self._day_high, hi)
        self._day_low = lo if self._day_low is None else min(self._day_low, lo)
        self._day_close = cl

        if self._target is None or self._sl_pips is None:
            return

        if ctx.position is not None:
            if ctx.position.side != self._target:
                ctx.close_position()
            return

        tp_pips = 10.0 * self._sl_pips  # exits come from flips, not targets
        if self._target > 0:
            ctx.buy(self._sl_pips, tp_pips)
        else:
            ctx.sell(self._sl_pips, tp_pips)
