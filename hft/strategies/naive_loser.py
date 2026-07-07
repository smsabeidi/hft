"""RandomFlipper — the falsification strategy.

Enters a random direction every `every_bars` bars with a tight symmetric
stop/target. It has zero informational edge by construction, so after spread,
slippage, and commission its expectancy MUST be negative. If the harness shows
it flat or profitable, the harness (or the data) is broken.

This is the first gate in the design doc's success criteria: a truth machine
must be able to lose.
"""

from __future__ import annotations

import numpy as np

from hft.backtest.engine import Context
from hft.strategies.base import BaseStrategy


class RandomFlipper(BaseStrategy):
    def __init__(self, every_bars: int = 15, sl_pips: float = 6.0, tp_pips: float = 6.0, seed: int = 7):
        self.every_bars = every_bars
        self.sl_pips = sl_pips
        self.tp_pips = tp_pips
        self.rng = np.random.default_rng(seed)

    def on_bar(self, ctx: Context) -> None:
        if ctx.position is not None:
            return
        if ctx.i % self.every_bars != 0:
            return
        if self.rng.random() < 0.5:
            ctx.buy(self.sl_pips, self.tp_pips)
        else:
            ctx.sell(self.sl_pips, self.tp_pips)
