# MQL5 execution layer

This layer runs on the Windows VPS inside MT5. It cannot be compiled or tested
on macOS — compiling and the parity gate are VPS-phase steps (days 31-60 in
the design doc schedule). Nothing here goes near a demo account until the
strategy has passed the Python harness gauntlet.

## Files

- `Include/RiskEngine.mqh` — prop-firm risk engine. Mirrors
  `hft/risk/engine.py` method-for-method. Change the Python reference first,
  then this file, then re-run the parity gate.
- `Experts/SessionBreakout.mq5` — London-open breakout EA (candidate family,
  not a validated edge). Server-side SL/TP on every order, disconnect policy,
  restart re-sync, heartbeat, push notifications, parity CSV logging.

## Deploy checklist (Windows VPS)

1. Install MT5 from the chosen broker. Log into the DEMO account.
2. Copy `Include/RiskEngine.mqh` to `MQL5/Include/`, the EA to `MQL5/Experts/`.
3. Compile in MetaEditor (F7). Zero warnings is the bar.
4. Pin the firm rulebook numbers into the EA inputs and set
   `InpRulesVerified=true` — the EA refuses to run live/demo without it.
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
