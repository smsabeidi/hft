"""Strategy base. Strategies are CANDIDATE FAMILIES, not validated edges.

A family is a distinct entry hypothesis (design doc definition). Parameter
sweeps stay inside the family. Nothing here is presumed profitable until it
survives the harness gauntlet: backtest -> walk-forward -> parity -> demo.
Martingale, grid, and averaging-down are banned by the design doc's hard fail
condition — do not add them as families.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from hft.backtest.engine import Context


class BaseStrategy(ABC):
    #: subclasses declare their sweepable parameters for walk-forward grids
    param_grid: dict = {}

    @abstractmethod
    def on_bar(self, ctx: Context) -> None: ...
