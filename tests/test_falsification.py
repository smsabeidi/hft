"""The harness gate from the design doc's success criteria:

    "falsification test passes — a deliberately naive strategy shows negative
    after-cost expectancy. If the harness can't lose, it can't be trusted to win."
"""

from __future__ import annotations

from hft.backtest.costs import CostModel
from hft.backtest.engine import Backtester
from hft.backtest.metrics import compute_metrics
from hft.risk.engine import FirmConfig, RiskEngine
from hft.strategies.naive_loser import RandomFlipper
from tests.conftest import make_bars


def test_naive_strategy_loses_after_costs():
    bars = make_bars(7000, seed=99)  # ~5 trading days of M1
    cm = CostModel()
    cfg = FirmConfig(0.05, 0.10, 5.0, 0.005)
    bt = Backtester(cm, RiskEngine(cfg, 50_000.0, cm.pip_value_per_lot), 50_000.0)
    res = bt.run(bars, RandomFlipper(every_bars=15, sl_pips=6.0, tp_pips=6.0, seed=7))
    m = compute_metrics(res.trades, res.equity)
    assert m.n_trades >= 50
    # zero-edge + real costs must lose, and confidently so
    assert m.expectancy_usd < 0
    assert m.expectancy_ci_high < 0


def test_costless_random_is_roughly_flat():
    """Sanity check the other direction: with zero costs the same strategy
    should be near zero expectancy — proving the losses above come from the
    cost model, not an engine bias. The bars themselves must carry ZERO
    spread here: the engine prefers the bar's recorded spread over the cost
    model default, so a 'costless' CostModel over 0.7-pip bars is not
    costless (review finding #4)."""
    bars = make_bars(7000, seed=99, spread_pips=0.0)
    cm = CostModel(
        default_spread_pips=0.0,
        commission_per_lot_side=0.0,
        slippage_pips=0.0,
        swap_long_pips_per_day=0.0,
        swap_short_pips_per_day=0.0,
    )
    cfg = FirmConfig(0.05, 0.10, 5.0, 0.005)
    bt = Backtester(cm, RiskEngine(cfg, 50_000.0, cm.pip_value_per_lot), 50_000.0)
    res = bt.run(bars, RandomFlipper(every_bars=15, sl_pips=6.0, tp_pips=6.0, seed=7))
    m = compute_metrics(res.trades, res.equity)
    assert m.n_trades >= 50
    # zero-cost random trading: expectancy CI should straddle zero
    assert m.expectancy_ci_low < 0 < m.expectancy_ci_high
