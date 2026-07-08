"""fx_carry_xs — cross-sectional carry, round 2 of the fx_carry family.

Implements EXACTLY the frozen amendment in reports/c7_preregistration.md:
7 currencies vs USD, causal 3m differentials, weekly Friday rebalance with
weights applied from the next trading day, long top-k / short bottom-k,
retail swap markup on gross, 0.85bp/side turnover cost on weight changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from hft.strategies.carry import daily_bars_from_m1

TRADING_DAYS = 252
COST_SIDE = 0.85e-4  # 0.85bp of notional per unit turnover, per side

# quote conventions: value = +1 if long-currency return = +dln(pair)
PAIRS = {
    "EUR": ("EURUSD", +1), "GBP": ("GBPUSD", +1),
    "AUD": ("AUDUSD", +1), "NZD": ("NZDUSD", +1),
    "JPY": ("USDJPY", -1), "CAD": ("USDCAD", -1), "CHF": ("USDCHF", -1),
}
RATE_STEMS = {
    "USD": "USD_DTB3", "EUR": "EUR_ECBDFR", "GBP": "GBP_IR3TIB01GBM156N",
    "AUD": "AUD_IR3TIB01AUM156N", "JPY": "JPY_IR3TIB01JPM156N",
    "CHF": "CHF_IR3TIB01CHM156N", "CAD": "CAD_IR3TIB01CAM156N",
    "NZD": "NZD_IR3TIB01NZM156N",
}

GRID = {"k": [1, 2], "inv_vol": [False, True]}
TRAIN_N, TEST_N, ROLL_N = 500, 120, 120


@dataclass(frozen=True)
class XSParams:
    k: int = 1
    inv_vol: bool = False
    markup_pct: float = 1.0


def build_panel(bars_dir: Path, rates_dir: Path) -> pd.DataFrame:
    """MultiIndex-free wide panel: ret_<CCY>, diff_<CCY>, vol_<CCY> columns
    on a union trading-day index. diff and vol are CAUSAL (shifted)."""
    rets = {}
    for ccy, (pair, sign) in PAIRS.items():
        files = sorted(bars_dir.glob(f"{pair}_M1_*.parquet"))
        if not files:
            continue
        m1 = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
        bars = daily_bars_from_m1(m1.sort_values("time")).set_index("day")
        rets[ccy] = sign * np.log(bars["close"]).diff()
    returns = pd.DataFrame(rets).sort_index()

    rates = {}
    for ccy, stem in RATE_STEMS.items():
        df = pd.read_parquet(rates_dir / f"{stem}.parquet")
        rates[ccy] = df.set_index("date")["rate"]
    rate_panel = pd.DataFrame(rates).reindex(
        pd.date_range(returns.index.min() - pd.Timedelta(days=400),
                      returns.index.max(), freq="D")
    ).ffill().reindex(returns.index)

    out = pd.DataFrame(index=returns.index)
    for ccy in rets:
        out[f"ret_{ccy}"] = returns[ccy]
        out[f"diff_{ccy}"] = (rate_panel[ccy] - rate_panel["USD"]).shift(1)
        vol = returns[ccy].rolling(60).std() * np.sqrt(TRADING_DAYS)
        out[f"vol_{ccy}"] = vol.shift(1)
    return out.iloc[1:]  # drop the first all-NaN return row


def _weights_for_day(row: pd.Series, ccys: list[str], p: XSParams) -> dict[str, float]:
    ranked = [(c, row[f"diff_{c}"]) for c in ccys if pd.notna(row[f"diff_{c}"])]
    if len(ranked) < 2 * p.k:
        return {}
    ranked.sort(key=lambda x: x[1])
    shorts = [c for c, _ in ranked[: p.k]]
    longs = [c for c, _ in ranked[-p.k:]]

    def side(names, sign):
        if p.inv_vol:
            iv = {c: 1.0 / row[f"vol_{c}"] if pd.notna(row[f"vol_{c}"]) and row[f"vol_{c}"] > 0
                  else 0.0 for c in names}
            tot = sum(iv.values())
            if tot <= 0:
                return {c: sign / len(names) for c in names}
            return {c: sign * iv[c] / tot for c in names}
        return {c: sign / len(names) for c in names}

    w = side(longs, +1.0)
    w.update(side(shorts, -1.0))
    return w


def run_xs(panel: pd.DataFrame, p: XSParams) -> pd.Series:
    """Daily after-cost portfolio returns per the frozen spec."""
    ccys = sorted(c.split("_", 1)[1] for c in panel.columns if c.startswith("ret_"))
    idx = panel.index
    is_friday = pd.Series(idx.dayofweek == 4, index=idx)

    weights = {c: 0.0 for c in ccys}
    pnl = np.zeros(len(idx))
    pending: dict[str, float] | None = None
    for i, (day, row) in enumerate(panel.iterrows()):
        if pending is not None:  # weights decided at last close apply today
            turnover = sum(abs(pending.get(c, 0.0) - weights.get(c, 0.0)) for c in ccys)
            pnl[i] -= turnover * COST_SIDE
            weights = {c: pending.get(c, 0.0) for c in ccys}
            pending = None
        gross = sum(abs(w) for w in weights.values())
        for c in ccys:
            w = weights[c]
            if w == 0.0:
                continue
            r = row[f"ret_{c}"]
            d = row[f"diff_{c}"]
            pnl[i] += w * (0.0 if pd.isna(r) else r)
            pnl[i] += w * (0.0 if pd.isna(d) else d) / 100.0 / TRADING_DAYS
        pnl[i] -= p.markup_pct / 100.0 / TRADING_DAYS * gross
        if is_friday.iloc[i]:
            pending = _weights_for_day(row, ccys, p)
    return pd.Series(pnl, index=idx)


@dataclass
class XSWindow:
    test_start: object
    params: dict
    train_net: float
    test_net: float
    test_weeks: int


def walk_forward_xs(panel: pd.DataFrame, markup_pct: float) -> tuple[list[XSWindow], pd.Series]:
    windows: list[XSWindow] = []
    oos_weekly: list[pd.Series] = []
    start = 0
    n = len(panel)
    while start + TRAIN_N + TEST_N <= n:
        train = panel.iloc[start : start + TRAIN_N]
        test = panel.iloc[start + TRAIN_N : start + TRAIN_N + TEST_N]

        best, best_net = None, float("-inf")
        for combo in product(*GRID.values()):
            p = XSParams(*combo, markup_pct=markup_pct)
            net = float(run_xs(train, p).sum())
            if net > best_net:
                best_net, best = net, combo
        p = XSParams(*best, markup_pct=markup_pct)
        daily = run_xs(test, p)
        weekly = daily.resample("W-FRI").sum()
        weekly = weekly[weekly.index.isin(daily.resample("W-FRI").count()[lambda s: s > 0].index)]
        windows.append(
            XSWindow(test.index[0].date(), dict(zip(GRID, best)), best_net,
                     float(daily.sum()), len(weekly))
        )
        oos_weekly.append(weekly)
        start += ROLL_N
    pooled = pd.concat(oos_weekly) if oos_weekly else pd.Series(dtype=float)
    return windows, pooled
