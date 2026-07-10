"""One-day HF backtest for Dollar MODE_DEMO_HF — concurrency accounting +
loss-rate dial.

Mirrors the EA's HF logic on real EURUSD M1 (bracket resolution at M1 OHLC,
stop-priority within a bar, strict direction alternation, ms cadence floor,
max-open cap). Answers two questions the founder asked:
  1. how many positions are open through a day at a given cadence/cap?
  2. how does the loss RATE move as we widen SL:TP geometry toward ~0% —
     and what does each notch cost in expectancy (the whole point)?

Honesty invariant baked in: entries are SIGNAL-FREE (alternating), so any
win rate reported is pure geometry sl/(tp+sl), and any expectancy is the
cost line. If a config ever shows positive expectancy on this signal-free
book, the simulator is broken.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

PIP = 0.0001
COST_RT_PIPS = 1.05  # friendly: 0.25 spread + 0.7 commission + 0.1 slippage


@dataclass
class HFConfig:
    tp_pips: float
    sl_pips: float
    cadence_ms: int = 1000
    max_open: int = 50
    label: str = ""


@dataclass
class HFDayResult:
    label: str
    tp_pips: float
    sl_pips: float
    entries: int
    peak_concurrent: int
    avg_concurrent: float
    wins: int
    losses: int
    open_at_eod: int
    net_pips: float

    @property
    def closed(self) -> int:
        return self.wins + self.losses

    @property
    def loss_rate(self) -> float:
        return self.losses / self.closed if self.closed else 0.0

    @property
    def win_rate(self) -> float:
        return self.wins / self.closed if self.closed else 0.0

    @property
    def exp_per_trade(self) -> float:
        return self.net_pips / self.closed if self.closed else 0.0


def simulate_hf_day(bars: pd.DataFrame, cfg: HFConfig) -> HFDayResult:
    """bars: one day of M1 (time, open, high, low, close), tz-aware UTC."""
    o = bars["open"].to_numpy()
    h = bars["high"].to_numpy()
    lo = bars["low"].to_numpy()
    t_ms = (bars["time"].astype("int64") // 10**6).to_numpy()
    n = len(bars)
    tp, sl = cfg.tp_pips * PIP, cfg.sl_pips * PIP

    # open positions: list of (entry_px, dir, tp_px, sl_px)
    open_pos: list[tuple[float, int, float, float]] = []
    direction = 1
    next_entry_ms = 0
    entries = wins = losses = 0
    net_pips = 0.0
    peak_concurrent = 0
    concurrent_area = 0  # sum of open-count per bar, for time-avg

    for i in range(n):
        # 1) resolve open positions on THIS bar (stop priority)
        still_open = []
        for (epx, d, tpx, spx) in open_pos:
            hit_stop = (lo[i] <= spx) if d > 0 else (h[i] >= spx)
            hit_tp = (h[i] >= tpx) if d > 0 else (lo[i] <= tpx)
            if hit_stop:
                losses += 1
                net_pips += -cfg.sl_pips - COST_RT_PIPS
            elif hit_tp:
                wins += 1
                net_pips += cfg.tp_pips - COST_RT_PIPS
            else:
                still_open.append((epx, d, tpx, spx))
        open_pos = still_open

        # 2) attempt new entry (cadence floor + cap), alternating direction
        if t_ms[i] >= next_entry_ms and len(open_pos) < cfg.max_open:
            entry = o[i]
            if direction > 0:
                open_pos.append((entry, 1, entry + tp, entry - sl))
            else:
                open_pos.append((entry, -1, entry - tp, entry + sl))
            direction = -direction
            entries += 1
            next_entry_ms = t_ms[i] + cfg.cadence_ms

        peak_concurrent = max(peak_concurrent, len(open_pos))
        concurrent_area += len(open_pos)

    # close survivors at final close (EOD flatten), counted at mark
    eod = len(open_pos)
    for (epx, d, tpx, spx) in open_pos:
        mark = (bars["close"].iloc[-1] - epx) / PIP * d
        net_pips += mark - COST_RT_PIPS
        if mark >= 0:
            wins += 1
        else:
            losses += 1

    return HFDayResult(
        label=cfg.label or f"tp{cfg.tp_pips:g}/sl{cfg.sl_pips:g}",
        tp_pips=cfg.tp_pips, sl_pips=cfg.sl_pips,
        entries=entries, peak_concurrent=peak_concurrent,
        avg_concurrent=concurrent_area / n if n else 0.0,
        wins=wins, losses=losses, open_at_eod=eod, net_pips=net_pips,
    )


def load_one_day(parquet_glob_dir, symbol_stem: str, day: str) -> pd.DataFrame:
    from pathlib import Path
    files = sorted(Path(parquet_glob_dir).glob(f"{symbol_stem}_M1_*.parquet"))
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df = df.sort_values("time", ignore_index=True)
    d0 = pd.Timestamp(day, tz="UTC")
    return df[(df["time"] >= d0) & (df["time"] < d0 + pd.Timedelta(days=1))].reset_index(drop=True)
