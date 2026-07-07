"""London-open breakout of the Asian-session range. CANDIDATE, not an edge.

Hypothesis (the family): the Asian session (roughly 00:00-06:59 UTC on EURUSD)
builds a range; the London open (07:00 UTC) resolves it directionally often
enough, and with enough follow-through, to beat costs.

Rules:
- Track the high/low of bars inside the Asian window each day.
- In the London window, on the first close above the Asian high -> buy;
  below the Asian low -> sell. One entry per day maximum.
- SL at the opposite side of the range, clamped to [min_sl_pips, max_sl_pips].
- TP at k_tp x range size. Time-stop: close at session_end_hour UTC.
- Skip days whose range exceeds max_range_pips (news-distorted ranges).
"""

from __future__ import annotations

from hft.backtest.engine import Context
from hft.strategies.base import BaseStrategy


class SessionBreakout(BaseStrategy):
    param_grid = {
        "k_tp": [1.0, 1.5, 2.0],
        "max_range_pips": [25.0, 40.0],
    }

    def __init__(
        self,
        asian_start_hour: int = 0,
        asian_end_hour: int = 7,
        london_end_hour: int = 12,
        session_end_hour: int = 16,
        k_tp: float = 1.5,
        min_sl_pips: float = 8.0,
        max_sl_pips: float = 30.0,
        max_range_pips: float = 40.0,
        pip_size: float = 0.0001,
    ):
        self.asian_start_hour = asian_start_hour
        self.asian_end_hour = asian_end_hour
        self.london_end_hour = london_end_hour
        self.session_end_hour = session_end_hour
        self.k_tp = k_tp
        self.min_sl_pips = min_sl_pips
        self.max_sl_pips = max_sl_pips
        self.max_range_pips = max_range_pips
        self.pip_size = pip_size
        self._day = None
        self._hi = None
        self._lo = None
        self._traded_today = False

    def on_bar(self, ctx: Context) -> None:
        t = ctx.time
        if self._day != t.date():
            self._day = t.date()
            self._hi, self._lo = None, None
            self._traded_today = False

        hour = t.hour
        if self.asian_start_hour <= hour < self.asian_end_hour:
            self._hi = ctx.high if self._hi is None else max(self._hi, ctx.high)
            self._lo = ctx.low if self._lo is None else min(self._lo, ctx.low)
            return

        # time-stop
        if ctx.position is not None and hour >= self.session_end_hour:
            ctx.close_position()
            return

        if (
            ctx.position is not None
            or self._traded_today
            or self._hi is None
            or self._lo is None
            or not (self.asian_end_hour <= hour < self.london_end_hour)
        ):
            return

        range_pips = (self._hi - self._lo) / self.pip_size
        if range_pips <= 0 or range_pips > self.max_range_pips:
            return

        sl_pips = min(max(range_pips, self.min_sl_pips), self.max_sl_pips)
        tp_pips = self.k_tp * range_pips
        if ctx.close > self._hi:
            ctx.buy(sl_pips, tp_pips)
            self._traded_today = True
        elif ctx.close < self._lo:
            ctx.sell(sl_pips, tp_pips)
            self._traded_today = True
