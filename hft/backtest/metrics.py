"""Performance metrics: after-cost expectancy with confidence intervals,
Sharpe, drawdown. Win rate is computed but is a diagnostic, never a gate —
that is a premise of the design doc, not a style preference.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats


@dataclass
class Metrics:
    n_trades: int = 0
    expectancy_usd: float = 0.0
    expectancy_ci_low: float = 0.0
    expectancy_ci_high: float = 0.0
    t_stat: float = 0.0
    win_rate: float = 0.0  # diagnostic only
    profit_factor: float = 0.0
    total_pnl_usd: float = 0.0
    sharpe_annual: float = 0.0
    max_drawdown_frac: float = 0.0
    max_daily_loss_frac: float = 0.0
    extras: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "extras"}
        d.update(self.extras)
        return d

    def summary(self) -> str:
        return (
            f"trades: {self.n_trades}\n"
            f"expectancy: ${self.expectancy_usd:.2f}/trade "
            f"(95% CI [{self.expectancy_ci_low:.2f}, {self.expectancy_ci_high:.2f}], t={self.t_stat:.2f})\n"
            f"total pnl: ${self.total_pnl_usd:.2f}\n"
            f"profit factor: {self.profit_factor:.2f}   win rate (diagnostic): {self.win_rate:.1%}\n"
            f"sharpe (annualized): {self.sharpe_annual:.2f}\n"
            f"max drawdown: {self.max_drawdown_frac:.2%}   worst day: {self.max_daily_loss_frac:.2%}"
        )


def compute_metrics(
    trades: pd.DataFrame,
    equity: pd.DataFrame,
    ci: float = 0.95,
) -> Metrics:
    """trades: needs column pnl_usd (net, after all costs) and exit_time.
    equity: columns time, equity."""
    m = Metrics()
    if trades is not None and len(trades):
        pnl = trades["pnl_usd"].to_numpy(dtype=float)
        m.n_trades = len(pnl)
        m.expectancy_usd = float(pnl.mean())
        m.total_pnl_usd = float(pnl.sum())
        if len(pnl) > 1 and pnl.std(ddof=1) > 0:
            sem = pnl.std(ddof=1) / np.sqrt(len(pnl))
            lo, hi = stats.t.interval(ci, df=len(pnl) - 1, loc=pnl.mean(), scale=sem)
            m.expectancy_ci_low, m.expectancy_ci_high = float(lo), float(hi)
            m.t_stat = float(pnl.mean() / sem)
        else:
            m.expectancy_ci_low = m.expectancy_ci_high = m.expectancy_usd
        wins = pnl[pnl > 0]
        losses = pnl[pnl < 0]
        m.win_rate = float(len(wins) / len(pnl)) if len(pnl) else 0.0
        gross_loss = float(-losses.sum())
        m.profit_factor = float(wins.sum() / gross_loss) if gross_loss > 0 else float("inf") if len(wins) else 0.0

    if equity is not None and len(equity) > 1:
        eq = equity.set_index("time")["equity"].astype(float)
        daily = eq.resample("1D").last().dropna()
        rets = daily.pct_change().dropna()
        if len(rets) > 1 and rets.std(ddof=1) > 0:
            m.sharpe_annual = float(rets.mean() / rets.std(ddof=1) * np.sqrt(252))
        if len(rets):
            m.max_daily_loss_frac = float(-rets.min()) if rets.min() < 0 else 0.0
        running_max = eq.cummax()
        dd = (eq - running_max) / running_max
        m.max_drawdown_frac = float(-dd.min()) if len(dd) else 0.0

    return m
