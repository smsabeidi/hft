# MQL5 execution layer

This layer runs on the Windows VPS inside MT5. It cannot be compiled or tested
on macOS — compiling and the parity gate are VPS-phase steps (days 31-60 in
the design doc schedule). Nothing here goes near a demo account until the
strategy has passed the Python harness gauntlet.

## Files

- `Include/RiskEngine.mqh` — prop-firm risk engine. Mirrors
  `hft/risk/engine.py` method-for-method. Change the Python reference first,
  then this file, then re-run the parity gate.
- `Experts/SessionBreakout.mq5` — London-open breakout EA (family REFUTED in
  round 1 — kept as the reference implementation of the live-ops pattern;
  never deploy it). Server-side SL/TP on every order, disconnect policy,
  restart re-sync, heartbeat, push notifications, parity CSV logging.
- `Experts/InfraShadow.mq5` — infrastructure bring-up EA that TRADES
  NOTHING (no OrderSend in the file — grep it). Deploy THIS first, on demo:
  it proves risk telemetry, heartbeat, push notifications, common-file
  logging, and connectivity handling end-to-end, so a validated strategy
  later drops into a verified pipeline. This is the sanctioned "launch
  today" while no strategy has passed the gauntlet.
- `Include/FirmConfig.mqh` — GENERATED from `config/ftmo_50k.json` by
  `scripts/gen_firm_config.py`; never hand-edit. The JSON is the single
  source of truth for firm limits; EAs written after 2026-07-07 include this
  and refuse demo/live while `FIRM_RULES_VERIFIED` is false.

## Deploy checklist (Windows VPS)

1. Install MT5 from the chosen broker. Log into the DEMO account.
2. Copy `Include/RiskEngine.mqh` to `MQL5/Include/`, the EA to `MQL5/Experts/`.
3. Compile in MetaEditor (F7). Zero warnings is the bar.
4. Pin the firm rulebook into `config/ftmo_50k.json` (flip `verified` to
   true only with a dated rulebook version in hand), run
   `python3 scripts/gen_firm_config.py`, and copy the regenerated
   `Include/FirmConfig.mqh` alongside the other includes. Never type risk
   numbers into EA inputs by hand — transcription typos in drawdown
   constants are an account-killing failure mode.
5. Enable push notifications (Tools → Options → Notifications) with your
   MetaQuotes ID so halts and fills reach your phone.
6. Windows Task Scheduler: auto-start MT5 on boot; enable auto-login.
7. Verify the heartbeat GlobalVariable (`HB_<magic>`) updates and the parity
   CSV appears in the COMMON files folder after the first Strategy Tester run.

## Parity gate (before demo)

1. Export the SAME Dukascopy tick window used by the Python harness and import
   it into MT5 as a custom symbol (or use the broker symbol only if you also
   re-run the Python side on the broker's exported ticks).
2. Strategy Tester: model = "Every tick based on real ticks", fixed spread off.
3. Run the EA; collect the parity CSV from the COMMON files folder.
4. Diff trade-by-trade against the Python trade log (entry/exit time, side,
   lots, prices). Every divergence must be explained by a documented
   cost-model difference. Unexplained divergence blocks demo promotion.
