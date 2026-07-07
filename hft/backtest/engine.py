"""Event-driven, no-lookahead bar backtester with conservative fills.

Execution rules (the honesty layer — every rule biases AGAINST the strategy):
- Strategies decide on the CLOSE of bar i; market orders fill at the OPEN of
  bar i+1 (no lookahead by construction).
- Buys fill at ask (bid + bar spread) + slippage; sells at bid - slippage.
- Stops are checked intrabar. If both stop and target are touched inside one
  bar, the STOP is assumed to hit first (conservative).
- Stop fills take slippage; limit (take-profit) fills do not slip.
- Swap is charged per UTC day rollover, tripled on the configured weekday.
- Commission is charged per side.
- The risk engine marks equity every bar; a breach closes the position at the
  current bar close and halts the run — in the prop business a breach is death,
  and the backtest must experience it the same way the account would.

Granularity: bars (M1 by default) with per-bar recorded spread. This matches
the design doc's strategy class (holding minutes to days). It is NOT suitable
for strategies that live inside the bar.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd

from hft.backtest.costs import CostModel
from hft.risk.engine import RiskEngine


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

    @property
    def bar(self) -> pd.Series:
        return self.bars.iloc[self.i]

    @property
    def time(self) -> pd.Timestamp:
        return self.bars["time"].iloc[self.i]

    def history(self, n: int) -> pd.DataFrame:
        """Last n bars up to and including the current one. Never future bars."""
        lo = max(0, self.i - n + 1)
        return self.bars.iloc[lo : self.i + 1]

    def buy(self, sl_pips: float, tp_pips: float) -> None:
        self._pending = Order(+1, sl_pips, tp_pips)

    def sell(self, sl_pips: float, tp_pips: float) -> None:
        self._pending = Order(-1, sl_pips, tp_pips)

    def close(self) -> None:
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

    # --- price helpers ------------------------------------------------------
    def _ask(self, bid_price: float, bar) -> float:
        return bid_price + self.costs.spread(bar.get("spread"))

    # --- main loop ------------------------------------------------------------
    def run(self, bars: pd.DataFrame, strategy: Strategy) -> "BacktestResult":
        bars = bars.reset_index(drop=True)
        ctx = Context()
        ctx.bars = bars

        balance = self.initial_balance
        equity = balance
        position: Position | None = None
        trades: list[dict] = []
        equity_rows: list[tuple] = []
        halted_at: pd.Timestamp | None = None

        pipv = self.costs.pip_value_per_lot
        pip = self.costs.pip_size
        prev_date = None

        for i in range(len(bars)):
            bar = bars.iloc[i]
            t = bar["time"]
            date = t.date()

            # --- day rollover: swap + risk anchor ---------------------------
            if prev_date is not None and date != prev_date:
                if position is not None:
                    wd = pd.Timestamp(t).dayofweek
                    position.swap_usd += self.costs.swap(position.side, position.lots, [wd])
                self.risk.on_day_start(balance, equity)
            prev_date = date

            # --- execute pending decisions from the previous bar ------------
            if position is not None and ctx._close_requested:
                # decision was made on the previous bar's close -> fill at this bar's OPEN
                if position.side > 0:
                    px = bar["open"] - self.costs.slippage()
                else:
                    px = self._ask(bar["open"], bar) + self.costs.slippage()
                balance, trade = self._close_position(
                    position, bar, t, balance, reason="close", price=px
                )
                trades.append(trade)
                position = None
            ctx._close_requested = False

            if position is None and ctx._pending is not None and halted_at is None:
                o = ctx._pending
                lots = self.risk.allowed_lots(o.sl_pips, equity)
                if lots > 0:
                    if o.side > 0:
                        fill = self._ask(bar["open"], bar) + self.costs.slippage()
                        sl = fill - o.sl_pips * pip
                        tp = fill + o.tp_pips * pip
                    else:
                        fill = bar["open"] - self.costs.slippage()
                        sl = fill + o.sl_pips * pip
                        tp = fill - o.tp_pips * pip
                    balance -= self.costs.commission(lots)
                    position = Position(o.side, lots, t, fill, sl, tp)
            ctx._pending = None

            # --- intrabar stop/target checks (conservative: stop first) -----
            if position is not None:
                exit_price, reason = self._check_exits(position, bar)
                if exit_price is not None:
                    balance, trade = self._close_position(
                        position, bar, t, balance, reason=reason, price=exit_price
                    )
                    trades.append(trade)
                    position = None

            # --- mark equity and risk-check ----------------------------------
            unrealized = 0.0
            if position is not None:
                unrealized = self._unrealized(position, bar)
            equity = balance + unrealized
            equity_rows.append((t, equity, balance))

            if self.risk.on_mark(equity, t):
                # breach: liquidate at current close, halt everything
                if position is not None:
                    balance, trade = self._close_position(
                        position, bar, t, balance, reason="risk_breach"
                    )
                    trades.append(trade)
                    position = None
                equity = balance
                halted_at = t

            # --- let the strategy decide (fills next bar) --------------------
            if halted_at is None:
                ctx.i = i
                ctx.position = position
                strategy.on_bar(ctx)

        # close any open position at the last bar for accounting completeness
        if position is not None:
            last = bars.iloc[-1]
            balance, trade = self._close_position(
                position, last, last["time"], balance, reason="end_of_data"
            )
            trades.append(trade)

        trades_df = pd.DataFrame(trades)
        equity_df = pd.DataFrame(equity_rows, columns=["time", "equity", "balance"])
        return BacktestResult(trades_df, equity_df, halted_at, list(self.risk.violations))

    # --- helpers --------------------------------------------------------------
    def _unrealized(self, p: Position, bar) -> float:
        if p.side > 0:
            px_pnl = (bar["close"] - p.entry_price) * self.costs.contract_size * p.lots
        else:
            ask_close = self._ask(bar["close"], bar)
            px_pnl = (p.entry_price - ask_close) * self.costs.contract_size * p.lots
        return px_pnl + p.swap_usd

    def _check_exits(self, p: Position, bar) -> tuple[float | None, str]:
        spread = self.costs.spread(bar.get("spread"))
        slip = self.costs.slippage()
        if p.side > 0:
            # long: exits are sells at bid. A gap through the stop fills at the
            # open (worse), never at the stop price — gaps don't honor stops.
            if bar["low"] <= p.sl_price:
                return min(p.sl_price, bar["open"]) - slip, "stop"
            if bar["high"] >= p.tp_price:
                return p.tp_price, "target"
        else:
            # short: exits are buys at ask
            ask_open = bar["open"] + spread
            ask_high = bar["high"] + spread
            ask_low = bar["low"] + spread
            if ask_high >= p.sl_price:
                return max(p.sl_price, ask_open) + slip, "stop"
            if ask_low <= p.tp_price:
                return p.tp_price, "target"
        return None, ""

    def _close_position(
        self, p: Position, bar, t, balance: float, reason: str, price: float | None = None
    ) -> tuple[float, dict]:
        slip = self.costs.slippage()
        if price is None:
            if p.side > 0:
                price = bar["close"] - slip  # sell at bid
            else:
                price = self._ask(bar["close"], bar) + slip  # buy at ask
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
