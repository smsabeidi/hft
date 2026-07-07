"""Cost model: spread, commission, slippage, swap.

Conventions (used everywhere in the harness — the MQL5 side mirrors them):
- All quoted prices are BID. Buying pays the ask = bid + spread.
- pip_size: 0.0001 on EURUSD. pip value per standard lot on USD-quote pairs is
  pip_size * contract_size = $10. The model assumes a USD-quote pair and a USD
  account; extend before trading anything else.
- Slippage is adverse on every market/stop fill, zero on limit fills.
- Swap is charged per UTC-midnight rollover held. triple_swap_weekday is the
  weekday of the NEW day at rollover: under T+2 the Wed->Thu rollover carries
  the weekend value-date jump, so the default is Thursday (3). This
  approximates the 17:00 NY rollover — documented, deliberate, and
  recalibrated against the demo broker at the demo gate.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostModel:
    pip_size: float = 0.0001
    contract_size: float = 100_000.0
    default_spread_pips: float = 0.7
    commission_per_lot_side: float = 3.5  # USD, raw-spread account typical
    slippage_pips: float = 0.2
    swap_long_pips_per_day: float = -0.55
    swap_short_pips_per_day: float = 0.15
    triple_swap_weekday: int = 3  # weekday of the NEW day: Thursday (Monday=0)

    @property
    def pip_value_per_lot(self) -> float:
        return self.pip_size * self.contract_size  # $10/pip/lot on EURUSD

    def spread(self, bar_spread: float | None) -> float:
        """Spread in price units; prefer the bar's recorded spread."""
        if bar_spread is not None and bar_spread > 0:
            return bar_spread
        return self.default_spread_pips * self.pip_size

    def slippage(self) -> float:
        return self.slippage_pips * self.pip_size

    def commission(self, lots: float) -> float:
        """One side, USD."""
        return self.commission_per_lot_side * lots

    def swap(self, side: int, lots: float, rollovers: list[int]) -> float:
        """USD swap for a list of rollovers, each given as the weekday of the new day."""
        pips_per_day = (
            self.swap_long_pips_per_day if side > 0 else self.swap_short_pips_per_day
        )
        nights = sum(3 if wd == self.triple_swap_weekday else 1 for wd in rollovers)
        return pips_per_day * nights * self.pip_value_per_lot * lots

    def round_trip_cost_usd(self, lots: float, bar_spread: float | None = None) -> float:
        """Expected cost of an immediate open+close (no swap): spread + 2x slippage + 2x commission."""
        px_cost = self.spread(bar_spread) + 2 * self.slippage()
        return px_cost * self.contract_size * lots + 2 * self.commission(lots)
