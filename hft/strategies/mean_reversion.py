"""Z-score mean reversion. CANDIDATE, not an edge.

Hypothesis (the family): short-horizon EURUSD moves that stretch far from
their rolling mean revert often enough, net of costs, to be tradable during
liquid hours.

Rules:
- z = (close - rolling_mean(window)) / rolling_std(window)
- Enter against the stretch when |z| > z_in (long if z < -z_in, short if z > z_in),
  only between trade_start_hour and trade_end_hour UTC.
- Exit when |z| < z_out (reversion done) via ctx.close(); protective SL at
  sl_pips; TP far (rely on z-exit) at tp_pips.
"""

from __future__ import annotations

import numpy as np

from hft.backtest.engine import Context
from hft.strategies.base import BaseStrategy


class MeanReversion(BaseStrategy):
    param_grid = {
        "z_in": [2.0, 2.5, 3.0],
        "window": [60, 120],
    }

    def __init__(
        self,
        window: int = 60,
        z_in: float = 2.5,
        z_out: float = 0.5,
        sl_pips: float = 15.0,
        tp_pips: float = 30.0,
        trade_start_hour: int = 7,
        trade_end_hour: int = 17,
    ):
        self.window = window
        self.z_in = z_in
        self.z_out = z_out
        self.sl_pips = sl_pips
        self.tp_pips = tp_pips
        self.trade_start_hour = trade_start_hour
        self.trade_end_hour = trade_end_hour

    def _z(self, ctx: Context) -> float | None:
        closes = ctx.closes(self.window)
        if len(closes) < self.window:
            return None
        mu = closes.mean()
        sd = closes.std(ddof=1)
        if sd == 0 or not np.isfinite(sd):
            return None
        return float((closes[-1] - mu) / sd)

    def on_bar(self, ctx: Context) -> None:
        z = self._z(ctx)
        if z is None:
            return

        if ctx.position is not None:
            if abs(z) < self.z_out:
                ctx.close_position()
            return

        hour = ctx.time.hour
        if not (self.trade_start_hour <= hour < self.trade_end_hour):
            return
        if z < -self.z_in:
            ctx.buy(self.sl_pips, self.tp_pips)
        elif z > self.z_in:
            ctx.sell(self.sl_pips, self.tp_pips)
