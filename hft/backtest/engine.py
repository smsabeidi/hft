"""Event-driven, no-lookahead bar backtester with conservative fills.

Execution rules (the honesty layer — every rule biases AGAINST the strategy):
- Strategies decide on the CLOSE of bar i; market orders fill at the OPEN of
  bar i+1 (no lookahead by construction).
- Buys fill at ask (bid + bar spread) + slippage; sells at bid - slippage.
- Stops are checked intrabar. If both stop and target are touched inside one
  bar, the STOP is assumed to hit first (conservative).
- Stop fills take slippage; limit (take-profit) fills do not slip. A gap
  through the stop fills at the OPEN (gaps don't honor stops).
- Swap is charged per UTC day rollover, tripled on the configured weekday.
- Commission is charged per side.
- Risk breaches are checked against the WORST intrabar equity a surviving
  position saw (the firm marks tick-by-tick, not on closes). A breach closes
  the position and halts the run — in the prop business a breach is death,
  and the backtest must experience it the same way the account would.

Granularity: bars (M1 by default) with per-bar recorded spread. This matches
the design doc's strategy class (holding minutes to days). It is NOT suitable
for strategies that live inside the bar.

Performance: the loop runs on pre-extracted numpy scalars (~10x faster than
row access). Strategies should use the fast Context accessors (ctx.open,
ctx.high, ctx.low, ctx.close, ctx.time, ctx.closes(n)); ctx.bar and
ctx.history(n) remain available but pay pandas row costs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd

from hft.backtest.costs import CostModel
from hft.risk.engine import RiskEngine

_NS_PER_DAY = 86_400_000_000_000


@dataclass
class Position:
    side: int  # +1 long, -1 short
    lots: float
    entry_time: pd.Timestamp
    entry_price: float  # actual fill (ask for long, bid for short), slippage included
    sl_price: float
    tp_price: float
    swap_usd: float = 0.0


@dataclass
class Order:
    side: int
    sl_pips: float
    tp_pips: float


class Context:
    """What a strategy sees on each bar. Decisions here execute next bar."""

    def __init__(self) -> None:
        self.bars: pd.DataFrame | None = None
        self.i: int = 0
        self.position: Position | None = None
        self._pending: Order | None = None
        self._close_requested: bool = False
        # fast arrays, set by the engine
        self._o = self._h = self._l = self._c = None
        self._times: list | None = None

    # --- fast scalar accessors (preferred) ---------------------------------
    @property
    def open(self) -> float:
        return float(self._o[self.i])

    @property
    def high(self) -> float:
        return float(self._h[self.i])

    @property
    def low(self) -> float:
        return float(self._l[self.i])

    @property
    def close(self) -> float:
        return float(self._c[self.i])

    @property
    def time(self) -> pd.Timestamp:
        return self._times[self.i]

    def closes(self, n: int) -> np.ndarray:
        """Last n closes up to and including the current bar (numpy view)."""
        lo = max(0, self.i - n + 1)
        return self._c[lo : self.i + 1]

    # --- compatibility accessors (pandas row costs) -------------------------
    @property
    def bar(self) -> pd.Series:
        return self.bars.iloc[self.i]

    def history(self, n: int) -> pd.DataFrame:
        """Last n bars up to and including the current one. Never future bars."""
        lo = max(0, self.i - n + 1)
        return self.bars.iloc[lo : self.i + 1]

    # --- orders --------------------------------------------------------------
    def buy(self, sl_pips: float, tp_pips: float) -> None:
        self._pending = Order(+1, sl_pips, tp_pips)

    def sell(self, sl_pips: float, tp_pips: float) -> None:
        self._pending = Order(-1, sl_pips, tp_pips)

    def close_position(self) -> None:
        self._close_requested = True


class Strategy(Protocol):
    def on_bar(self, ctx: Context) -> None: ...


class Backtester:
    def __init__(
        self,
        cost_model: CostModel,
        risk_engine: RiskEngine,
        initial_balance: float = 50_000.0,
    ):
        self.costs = cost_model
        self.risk = risk_engine
        self.initial_balance = float(initial_balance)

    # --- main loop ------------------------------------------------------------
    def run(self, bars: pd.DataFrame, strategy: Strategy) -> "BacktestResult":
        bars = bars.reset_index(drop=True)
        n = len(bars)
        o = bars["open"].to_numpy(dtype=float)
        h = bars["high"].to_numpy(dtype=float)
        l = bars["low"].to_numpy(dtype=float)
        c = bars["close"].to_numpy(dtype=float)
        sp = bars["spread"].to_numpy(dtype=float) if "spread" in bars.columns else None
        times = bars["time"].tolist()
        day_int = (bars["time"].astype("int64") // _NS_PER_DAY).to_numpy()
        weekday = ((day_int + 3) % 7).astype(int)  # 1970-01-01 was a Thursday (3)

        ctx = Context()
        ctx.bars = bars
        ctx._o, ctx._h, ctx._l, ctx._c = o, h, l, c
        ctx._times = times

        balance = self.initial_balance
        equity = balance
        position: Position | None = None
        trades: list[dict] = []
        equity_rows: list[tuple] = []
        halted_at: pd.Timestamp | None = None

        pip = self.costs.pip_size
        contract = self.costs.contract_size
        default_spread = self.costs.default_spread_pips * pip
        slip = self.costs.slippage()
        prev_day = -1

        for i in range(n):
            t = times[i]
            spread_i = sp[i] if sp is not None else -1.0
            if not spread_i > 0.0:
                spread_i = default_spread

            # --- day rollover: swap + risk anchor ---------------------------
            if prev_day != -1 and day_int[i] != prev_day:
                if position is not None:
                    position.swap_usd += self.costs.swap(
                        position.side, position.lots, [int(weekday[i])]
                    )
                self.risk.on_day_start(balance, equity)
            prev_day = day_int[i]

            # --- execute pending decisions from the previous bar ------------
            if position is not None and ctx._close_requested:
                # decision was made on the previous bar's close -> fill at this OPEN
                if position.side > 0:
                    px = o[i] - slip
                else:
                    px = o[i] + spread_i + slip
                balance, trade = self._close_position(
                    position, t, balance, reason="close", price=px
                )
                trades.append(trade)
                position = None
            ctx._close_requested = False

            if position is None and ctx._pending is not None and halted_at is None:
                order = ctx._pending
                lots = self.risk.allowed_lots(order.sl_pips, equity)
                if lots > 0:
                    if order.side > 0:
                        fill = o[i] + spread_i + slip
                        sl = fill - order.sl_pips * pip
                        tp = fill + order.tp_pips * pip
                    else:
                        fill = o[i] - slip
                        sl = fill + order.sl_pips * pip
                        tp = fill - order.tp_pips * pip
                    balance -= self.costs.commission(lots)
                    position = Position(order.side, lots, t, fill, sl, tp)
            ctx._pending = None

            # --- intrabar stop/target checks (conservative: stop first) -----
            if position is not None:
                exit_price, reason = self._check_exits(
                    position, o[i], h[i], l[i], spread_i, slip
                )
                if exit_price is not None:
                    balance, trade = self._close_position(
                        position, t, balance, reason=reason, price=exit_price
                    )
                    trades.append(trade)
                    position = None

            # --- mark equity and risk-check ----------------------------------
            # The firm marks tick-by-tick, so the risk check uses the WORST
            # intrabar equity a surviving position saw, not just the close.
            unrealized = 0.0
            worst_unrealized = 0.0
            if position is not None:
                if position.side > 0:
                    unrealized = (c[i] - position.entry_price) * contract * position.lots
                    worst_unrealized = (
                        (l[i] - position.entry_price) * contract * position.lots
                    )
                else:
                    unrealized = (
                        (position.entry_price - (c[i] + spread_i)) * contract * position.lots
                    )
                    worst_unrealized = (
                        (position.entry_price - (h[i] + spread_i)) * contract * position.lots
                    )
                unrealized += position.swap_usd
                worst_unrealized += position.swap_usd
            equity = balance + unrealized
            worst_equity = balance + min(unrealized, worst_unrealized)
            equity_rows.append((t, equity, balance))

            if self.risk.on_mark(worst_equity, t):
                # breach: liquidate at current close, halt everything
                if position is not None:
                    if position.side > 0:
                        px = c[i] - slip
                    else:
                        px = c[i] + spread_i + slip
                    balance, trade = self._close_position(
                        position, t, balance, reason="risk_breach", price=px
                    )
                    trades.append(trade)
                    position = None
                equity = balance
                # the breach bar's equity row must reflect the liquidation
                equity_rows[-1] = (t, equity, balance)
                halted_at = t

            # --- let the strategy decide (fills next bar) --------------------
            if halted_at is None:
                ctx.i = i
                ctx.position = position
                strategy.on_bar(ctx)

        # close any open position at the last bar for accounting completeness
        if position is not None:
            i = n - 1
            spread_i = sp[i] if sp is not None else -1.0
            if not spread_i > 0.0:
                spread_i = default_spread
            if position.side > 0:
                px = c[i] - slip
            else:
                px = c[i] + spread_i + slip
            balance, trade = self._close_position(
                position, times[i], balance, reason="end_of_data", price=px
            )
            trades.append(trade)

        trades_df = pd.DataFrame(trades)
        equity_df = pd.DataFrame(equity_rows, columns=["time", "equity", "balance"])
        return BacktestResult(trades_df, equity_df, halted_at, list(self.risk.violations))

    # --- helpers --------------------------------------------------------------
    @staticmethod
    def _check_exits(
        p: Position, open_: float, high: float, low: float, spread: float, slip: float
    ) -> tuple[float | None, str]:
        if p.side > 0:
            # long: exits are sells at bid. A gap through the stop fills at the
            # open (worse), never at the stop price — gaps don't honor stops.
            if low <= p.sl_price:
                return min(p.sl_price, open_) - slip, "stop"
            if high >= p.tp_price:
                return p.tp_price, "target"
        else:
            # short: exits are buys at ask
            ask_open = open_ + spread
            ask_high = high + spread
            ask_low = low + spread
            if ask_high >= p.sl_price:
                return max(p.sl_price, ask_open) + slip, "stop"
            if ask_low <= p.tp_price:
                return p.tp_price, "target"
        return None, ""

    def _close_position(
        self, p: Position, t, balance: float, reason: str, price: float
    ) -> tuple[float, dict]:
        if p.side > 0:
            px_pnl = (price - p.entry_price) * self.costs.contract_size * p.lots
        else:
            px_pnl = (p.entry_price - price) * self.costs.contract_size * p.lots
        exit_commission = self.costs.commission(p.lots)
        # entry commission was charged to balance at entry; report full RT here
        pnl = px_pnl + p.swap_usd - exit_commission - self.costs.commission(p.lots)
        balance = balance + px_pnl + p.swap_usd - exit_commission
        trade = {
            "entry_time": p.entry_time,
            "exit_time": t,
            "side": p.side,
            "lots": p.lots,
            "entry_price": p.entry_price,
            "exit_price": price,
            "swap_usd": p.swap_usd,
            "commission_usd": 2 * self.costs.commission(p.lots),
            "pnl_usd": pnl,
            "reason": reason,
        }
        return balance, trade


@dataclass
class BacktestResult:
    trades: pd.DataFrame
    equity: pd.DataFrame
    halted_at: pd.Timestamp | None
    violations: list

    @property
    def final_equity(self) -> float:
        return float(self.equity["equity"].iloc[-1]) if len(self.equity) else 0.0
