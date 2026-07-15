//+------------------------------------------------------------------+
//| Dollar.mq5 — the consolidated EA. Everything this project         |
//| validated, in one file, mode-selected at attach time.             |
//|                                                                   |
//| Built 2026-07-09 to the founder's "consolidate everything into    |
//| one" goal. It is ONE honest machine with a mode switch, not a     |
//| pile of promises. Every mode shares the same spine: FirmConfig-   |
//| generated risk limits, the risk engine (permanent breach halt +   |
//| anti-martingale equity throttle), server-side stops on every      |
//| order, the EA-permission guard, restart re-sync, parity CSV, and  |
//| push alerts.                                                      |
//|                                                                   |
//| MODES (input InpMode):                                            |
//|   MODE_WATCH   - trades nothing; risk telemetry + heartbeat +      |
//|                  alerts (the InfraShadow role). Runs anywhere.     |
//|   MODE_SESSION - London-open breakout, 1 trade/day, full risk      |
//|                  sizing (the SessionBreakout role). The rehearsal  |
//|                  strategy — refuted on 5.5y, ops-honest only.      |
//|   MODE_DEMO_HF - high-cadence geometry demo (the WinRate80 role):  |
//|                  seconds cadence, multi-position, ~86% win rate,   |
//|                  NEGATIVE expectancy printed live. Demo/tester      |
//|                  only, by hard guard. FIXED lot size by design     |
//|                  (the geometry demo shows the dial at constant      |
//|                  size) — the equity throttle applies to the         |
//|                  risk-sized modes (SESSION, SIGNAL), not this one.  |
//|                  Stops ARE server-side on every order here too.     |
//|   MODE_SIGNAL  - the throne: routes a VALIDATED signal from        |
//|                  GetSignal() through full risk + execution. Ships  |
//|                  a NULL provider — trades nothing until a family   |
//|                  passes the gauntlet + parity gate. This is where  |
//|                  a real edge is installed, and the ONLY mode meant |
//|                  to ever make money on a funded account.           |
//|                                                                   |
//| WHAT THIS EA IS NOT: it is not a validated MT5 money-maker, because|
//| none exists yet (rounds.log: 20 rounds, 1 PASS, and that PASS is a |
//| crypto spot+perp strategy MT5 cannot run). Dollar is the vessel,   |
//| fully rigged, waiting for cargo. It refuses to pretend otherwise.  |
//+------------------------------------------------------------------+
#property copyright "HFT harness"
#property version   "1.00"
#property description "Consolidated EA: watch/session/demo-HF/signal modes. Signal mode ships empty."
#property strict

#include <Trade\Trade.mqh>
#include <RiskEngine.mqh>
#include <FirmConfig.mqh>

enum EDollarMode { MODE_WATCH, MODE_SESSION, MODE_DEMO_HF, MODE_SIGNAL };

input EDollarMode InpMode           = MODE_WATCH;      // start safe: telemetry only
//--- risk (inherits the pinned FirmConfig; overridable per attach) ---
input double      InpInitialBalance = FIRM_ACCOUNT_TIER_USD;
input bool        InpRulesVerified  = FIRM_RULES_VERIFIED;
//--- SOFT daily circuit breaker (universal loss cap; works on any account,
//--- any mode; distinct from the permanent breach-halt — this one RESETS
//--- each day). Flattens + stands down when the day's loss hits the ceiling.
input double      InpDailyStopPct   = 3.0;   // % of day-start equity; 0 = off
input double      InpMaxTotalRiskPct = 5.0;  // cap aggregate open risk (SL x size) as % equity; 0 = off
//--- session mode (UTC) ---
input int         InpAsianEndHour   = 7;
input int         InpLondonEndHour  = 12;
input double      InpKTakeProfit    = 1.5;
input double      InpMinSlPips      = 8.0;
input double      InpMaxSlPips      = 30.0;
input double      InpMaxRangePips   = 40.0;
input int         InpMaxSpreadPts   = 12;
//--- demo-HF mode (industry-grade throughput pass, 2026-07-10) ---
input double      InpHFTakeProfit   = 10.0;
input double      InpHFStopLoss     = 60.0;
input int         InpHFCadenceMs    = 1000;  // min ms between entries (>=100)
input int         InpHFMaxOpen      = 50;    // concurrent positions (1..200)
input double      InpHFLots         = 1.0;
input bool        InpHFAsync        = true;  // async order submission (fire, ack via events)
input double      InpMinFreeMarginPct = 20.0; // stand down below this free-margin % of equity
//--- common ---
input long        InpMagic          = 20260900;
input string      InpParityLog      = "parity_dollar.csv";

CTrade      trade;
CRiskEngine risk;
double      g_pip;
int         g_srv_off_sec = 0;
double      g_asian_hi = 0.0, g_asian_lo = 0.0;
datetime    g_day = 0;
bool        g_traded_today = false;
datetime    g_last_bar = 0;
int         g_hf_dir = 1;

// --- hot-path caches (set once at init: no per-tick SymbolInfo calls) ---
double      g_stops_level_px = 0.0;  // broker min stop distance, price units
// --- event-sourced position counter (O(1) hot path) + reconciliation ----
int         g_open_count = 0;
datetime    g_last_reconcile = 0;
// --- cadence + latency instrumentation ---------------------------------
ulong       g_next_entry_us = 0;
double      g_submit_us_ema = 0.0;   // EMA of order-submission latency
long        g_sent = 0, g_acked = 0, g_rejected = 0;
// --- buffered journal: one persistent handle, flushed on heartbeat ------
int         g_journal_fh = INVALID_HANDLE;
uint        g_last_comment_ms = 0;
// --- soft daily circuit breaker (resets each server day) ----------------
datetime    g_breaker_day = 0;
double      g_day_start_equity = 0.0;
bool        g_stood_down_today = false;

string ParityFile() { return (MQLInfoInteger(MQL_TESTER) ? "tester_" : "live_") + InpParityLog; }
datetime UTCDay(const datetime t) { return (datetime)(t - (t % 86400)); }

//+------------------------------------------------------------------+
//| SIGNAL SLOT — the throne. A validated family (gauntlet + parity   |
//| PASS) is the ONLY thing that may be wired in here. Ships NULL.    |
//+------------------------------------------------------------------+
// Two-step arming: filling GetSignal() is not enough — MODE_SIGNAL refuses
// to trade until DOLLAR_SIGNAL_VALIDATED is ALSO flipped true, a deliberate
// second edit that no accidental/untested wiring of GetSignal can satisfy.
#define DOLLAR_SIGNAL_VALIDATED false

struct DollarSignal { int dir; double sl_pips; double tp_pips; };
bool GetSignal(DollarSignal &s)
  {
   return(false);   // NULL PROVIDER — no MT5 family has passed (rounds.log)
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   g_pip = (_Digits == 5 || _Digits == 3) ? 10.0 * _Point : _Point;
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(20);

   const bool tester = (bool)MQLInfoInteger(MQL_TESTER);
   const bool demo = (ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE)
                     == ACCOUNT_TRADE_MODE_DEMO;

   // EA-permission guard applies to every trading context (not the tester)
   if(!tester && EABannedHere())
      return(INIT_FAILED);

   // MODE_DEMO_HF is a negative-expectancy demonstration: demo/tester only
   if(InpMode == MODE_DEMO_HF && !tester && !demo)
     {
      Alert("Dollar MODE_DEMO_HF is a geometry demo (negative expectancy). ",
            "Demo or tester accounts only.");
      return(INIT_FAILED);
     }

   // trading modes need the rulebook pinned (tester exempt, like the others)
   const bool trades = (InpMode != MODE_WATCH);
   if(trades && !InpRulesVerified && !tester)
     {
      Alert("Dollar: firm rules not verified. Pin config, regenerate ",
            "FirmConfig.mqh, redeploy. Trading modes refuse until then.");
      return(INIT_FAILED);
     }

   ComputeServerOffset();   // sets g_srv_off_sec (server time minus UTC)
   PrintFormat("Dollar server-UTC offset: %+d min (auto) — VERIFY vs broker",
               g_srv_off_sec / 60);

   if(!risk.Init(InpInitialBalance, FIRM_DAILY_LOSS_FRAC, FIRM_TOTAL_DD_FRAC,
                 OWN_RISK_PER_TRADE, OWN_SAFETY_FACTOR, FIRM_MAX_LOTS,
                 "DOLLAR_" + (string)InpMagic))
      return(INIT_FAILED);

   g_day = UTCDay(TimeGMT());
   g_open_count = OurOpenScan();       // reconcile once, then event-sourced
   if(g_open_count > 0)
      g_traded_today = true;
   g_stops_level_px = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   ParityHeader();
   g_journal_fh = FileOpen(ParityFile(), FILE_READ | FILE_WRITE | FILE_CSV | FILE_COMMON, ',');
   if(g_journal_fh != INVALID_HANDLE)
      FileSeek(g_journal_fh, 0, SEEK_END);

   if(InpMode == MODE_DEMO_HF)
     {
      trade.SetAsyncMode(InpHFAsync);  // fire-and-forget; acks via OnTradeTransaction
      EventSetTimer(1);                // 1s timer = reconciliation + heartbeat only;
     }                                 // entries are TICK-driven with a ms cadence floor
   else
      EventSetTimer(60);

   PrintFormat("Dollar up: mode=%s firm=%s verified=%s ctx=%s | daily_floor=%.2f total_floor=%.2f",
               ModeName(InpMode), FIRM_NAME, InpRulesVerified ? "true" : "false",
               tester ? "tester" : (demo ? "DEMO" : "LIVE"),
               risk.DailyLossFloor(), risk.TotalDDFloor());
   if(InpMode == MODE_SIGNAL)
      Print("Dollar MODE_SIGNAL: DISARMED (slot NULL and DOLLAR_SIGNAL_VALIDATED=",
            DOLLAR_SIGNAL_VALIDATED ? "true" : "false",
            "). Will not trade until a family PASSES and the sentinel is flipped.");
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   if(g_journal_fh != INVALID_HANDLE) { FileClose(g_journal_fh); g_journal_fh = INVALID_HANDLE; }
   if(InpMode == MODE_DEMO_HF)
      PrintFormat("Dollar HF shutdown: sent=%d acked=%d rejected=%d "
                  "submit-latency EMA %.0f us", g_sent, g_acked, g_rejected, g_submit_us_ema);
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   if(risk.OnTickUpdate())          // permanent breach: flatten ours, halt forever
     {
      CloseOurPositions();
      return;
     }
   if(DailyBreakerTripped())        // soft daily cap: flatten + stand down (resets tomorrow)
      return;
   // HF entries ride the TICK stream (lowest latency MQL5 offers an EA),
   // gated by a millisecond cadence floor — not the 1s timer quantum
   if(InpMode == MODE_DEMO_HF && !risk.Halted())
      TryHFEntry();
  }

//+------------------------------------------------------------------+
//| Soft daily circuit breaker — the universal loss cap. Resets each  |
//| server day (unlike the permanent breach-halt). Returns true when  |
//| the day is stood down (caller must place no new entries).         |
//+------------------------------------------------------------------+
bool DailyBreakerTripped()
  {
   const datetime today = (datetime)(TimeCurrent() - (TimeCurrent() % 86400));
   if(today != g_breaker_day)       // new day: re-anchor, re-arm
     {
      g_breaker_day = today;
      g_day_start_equity = AccountInfoDouble(ACCOUNT_EQUITY);
      g_stood_down_today = false;
     }
   if(g_stood_down_today) return(true);
   if(InpDailyStopPct <= 0.0) return(false);
   const double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   if(g_day_start_equity > 0.0 &&
      eq <= g_day_start_equity * (1.0 - InpDailyStopPct / 100.0))
     {
      CloseOurPositions();          // includes floating losers — this is the point
      g_stood_down_today = true;
      Notify(StringFormat("DAILY STOP -%.1f%% hit: flattened, standing down to next day",
                          InpDailyStopPct));
      return(true);
     }
   return(false);
  }

//+------------------------------------------------------------------+
void OnTimer()
  {
   if(risk.Halted())
      return;
   Heartbeat();

   // HF housekeeping (reconcile/flush/banner) runs regardless of the breaker;
   // the daily stop only gates NEW entries, which for HF live on OnTick.
   if(InpMode == MODE_DEMO_HF)
     { HFHousekeeping(); return; }

   if(DailyBreakerTripped())        // soft daily cap gates timer-driven entries too
      return;
   if(!(bool)TerminalInfoInteger(TERMINAL_CONNECTED))
      return;                       // no new entries while disconnected

   switch(InpMode)
     {
      case MODE_WATCH:    return;                 // telemetry only
      case MODE_SESSION:  ManageSession();  break;
      case MODE_SIGNAL:   ManageSignal();   break;
      default: break;
     }
  }

//+------------------------------------------------------------------+
//| HF housekeeping (1s timer): reconcile the event-sourced counter,  |
//| flush the journal, refresh the on-chart truth banner.             |
//+------------------------------------------------------------------+
void HFHousekeeping()
  {
   const datetime now = TimeCurrent();
   if(now - g_last_reconcile >= 5)      // self-healing counter, every 5s
     {
      g_open_count = OurOpenScan();
      g_last_reconcile = now;
     }
   if(g_journal_fh != INVALID_HANDLE)
      FileFlush(g_journal_fh);
   Comment(StringFormat(
      "Dollar HF — GEOMETRY DEMO, NOT AN EDGE\n"
      "open %d/%d | sent %d acked %d rejected %d | submit EMA %.0f us\n"
      "win rate is the dial; expectancy <= 0 by measurement",
      g_open_count, (int)MathMax(MathMin(InpHFMaxOpen, 200), 1),
      g_sent, g_acked, g_rejected, g_submit_us_ema));
  }

//+------------------------------------------------------------------+
//| MODE_SESSION — London breakout of the Asian range, 1 trade/day.  |
//+------------------------------------------------------------------+
void ManageSession()
  {
   const datetime bar = iTime(_Symbol, PERIOD_M1, 0);
   if(bar == g_last_bar) return;
   g_last_bar = bar;

   // derive UTC from the SERVER-stamped closed bar + measured offset — robust
   // in the tester where TimeGMT() is unreliable; mirrors SessionBreakout so
   // the parity gate holds
   const datetime bar_utc = iTime(_Symbol, PERIOD_M1, 1) - g_srv_off_sec;
   MqlDateTime dt; TimeToStruct(bar_utc, dt);
   const datetime today = UTCDay(bar_utc);
   if(today != g_day) { g_day = today; g_asian_hi = 0; g_asian_lo = 0; g_traded_today = false; }

   // accumulate the Asian range up to InpAsianEndHour
   if(dt.hour < InpAsianEndHour)
     {
      const double hi = iHigh(_Symbol, PERIOD_M1, 1), lo = iLow(_Symbol, PERIOD_M1, 1);
      g_asian_hi = (g_asian_hi == 0) ? hi : MathMax(g_asian_hi, hi);
      g_asian_lo = (g_asian_lo == 0) ? lo : MathMin(g_asian_lo, lo);
      return;
     }
   if(g_traded_today || g_asian_hi == 0 || g_asian_lo == 0) return;
   if(dt.hour >= InpLondonEndHour) return;
   if(SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) > InpMaxSpreadPts) return;

   const double range_pips = (g_asian_hi - g_asian_lo) / g_pip;
   if(range_pips <= 0 || range_pips > InpMaxRangePips) return;
   const double sl_pips = MathMin(MathMax(range_pips, InpMinSlPips), InpMaxSlPips);
   const double tp_pips = InpKTakeProfit * range_pips;
   const double lots = SizedLots(sl_pips);
   if(lots <= 0) return;

   const double c = iClose(_Symbol, PERIOD_M1, 1);
   const double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   const double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(c > g_asian_hi &&
      trade.Buy(lots, _Symbol, 0.0, bid - sl_pips*g_pip, ask + tp_pips*g_pip, "Dollar session"))
      { g_traded_today = true; Notify("session BUY"); }
   else if(c < g_asian_lo &&
      trade.Sell(lots, _Symbol, 0.0, ask + sl_pips*g_pip, bid - tp_pips*g_pip, "Dollar session"))
      { g_traded_today = true; Notify("session SELL"); }
  }

//+------------------------------------------------------------------+
//| MODE_DEMO_HF — high-cadence geometry demo. Negative expectancy.  |
//+------------------------------------------------------------------+
void TryHFEntry()
  {
   // fixed InpHFLots BY DESIGN: this is a geometry demonstration, not a
   // risk-sized strategy — constant size is what makes the win-rate dial
   // legible. Demo-only guard (OnInit) is why bypassing the throttle is safe.
   const ulong now_us = GetMicrosecondCount();
   if(now_us < g_next_entry_us) return;                 // cadence floor
   if(g_open_count >= (int)MathMax(MathMin(InpHFMaxOpen, 200), 1)) return;

   // margin guard: professional books stand down before the broker makes them
   const double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(equity <= 0.0 ||
      AccountInfoDouble(ACCOUNT_MARGIN_FREE) < equity * InpMinFreeMarginPct / 100.0)
      return;

   // aggregate open-risk cap: N concurrent same-symbol positions are ONE
   // correlated bet, not N diversified ones — this bounds the total, which
   // is the tail that actually kills accounts. Refuse the entry that would
   // breach the ceiling. (Cap on the loss-side risk: (N+1) x SL x size.)
   if(InpMaxTotalRiskPct > 0.0)
     {
      const double tvpp = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE) *
                          (g_pip / SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE));
      const double per_pos_risk = InpHFStopLoss * tvpp * InpHFLots;
      if((g_open_count + 1) * per_pos_risk >
         AccountInfoDouble(ACCOUNT_EQUITY) * InpMaxTotalRiskPct / 100.0)
         return;   // adding this position would exceed the aggregate risk cap
     }

   const double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   const double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(ask <= 0 || bid <= 0) return;
   const double tp = InpHFTakeProfit * g_pip, sl = InpHFStopLoss * g_pip;
   if(tp < g_stops_level_px || sl < g_stops_level_px)
      return;   // broker min-stop distance: refuse rather than silently
                // widen (widening would falsify the win-rate geometry)

   g_next_entry_us = now_us + (ulong)MathMax(InpHFCadenceMs, 100) * 1000;
   const ulong t0 = GetMicrosecondCount();
   bool ok;
   if(g_hf_dir > 0) ok = trade.Buy(InpHFLots, _Symbol, 0.0, bid - sl, ask + tp, "Dollar HF");
   else             ok = trade.Sell(InpHFLots, _Symbol, 0.0, ask + sl, bid - tp, "Dollar HF");
   const double dt_us = (double)(GetMicrosecondCount() - t0);
   g_submit_us_ema = (g_submit_us_ema == 0.0) ? dt_us : 0.9 * g_submit_us_ema + 0.1 * dt_us;
   g_sent++;
   if(!ok) g_rejected++;
   g_hf_dir = -g_hf_dir;
  }

//+------------------------------------------------------------------+
//| MODE_SIGNAL — validated-edge throne. Ships NULL.                 |
//+------------------------------------------------------------------+
void ManageSignal()
  {
   if(!DOLLAR_SIGNAL_VALIDATED) return;   // throne disarmed: never trades
   const datetime bar = iTime(_Symbol, PERIOD_CURRENT, 0);
   if(bar == g_last_bar) return;
   g_last_bar = bar;
   if(OurOpenCount() > 0) return;
   DollarSignal s;
   if(!GetSignal(s) || s.dir == 0 || s.sl_pips <= 0 || s.tp_pips <= 0) return;
   const double lots = SizedLots(s.sl_pips);
   if(lots <= 0) return;
   const double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   const double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(s.dir > 0) trade.Buy(lots, _Symbol, 0.0, bid - s.sl_pips*g_pip, ask + s.tp_pips*g_pip, "Dollar signal");
   else          trade.Sell(lots, _Symbol, 0.0, ask + s.sl_pips*g_pip, bid - s.tp_pips*g_pip, "Dollar signal");
   Notify("signal fill");
  }

//+------------------------------------------------------------------+
//| shared helpers                                                    |
//+------------------------------------------------------------------+
double SizedLots(const double sl_pips)
  {
   const double tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   const double ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tv <= 0 || ts <= 0) return(0.0);
   return risk.AllowedLots(sl_pips, AccountInfoDouble(ACCOUNT_EQUITY), tv * (g_pip / ts));
  }

// full scan: init + periodic reconciliation only. The hot path reads the
// event-sourced g_open_count (O(1)) maintained in OnTradeTransaction.
int OurOpenScan()
  {
   int n = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      const ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpMagic) n++;
     }
   return(n);
  }

int OurOpenCount()
  {
   // non-HF modes hold <=1 position: the scan is cheap and always exact.
   // HF mode trusts the event counter between 5s reconciliations.
   return (InpMode == MODE_DEMO_HF) ? g_open_count : OurOpenScan();
  }

void CloseOurPositions()
  {
   // re-validate each ticket by select before closing (async close can shift
   // PositionsTotal mid-loop; mirrors SessionBreakout's close-by-ticket rule)
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      const ulong t = PositionGetTicket(i);
      if(t > 0 && PositionSelectByTicket(t) &&
         PositionGetInteger(POSITION_MAGIC) == InpMagic)
         trade.PositionClose(t);
     }
  }

void ComputeServerOffset()
  {
   const long raw = (long)TimeCurrent() - (long)TimeGMT();
   g_srv_off_sec = (int)(MathRound(raw / 1800.0) * 1800);   // nearest 30 min
  }

void Heartbeat() { GlobalVariableSet("HB_DOLLAR_" + (string)InpMagic, (double)TimeCurrent()); }
void Notify(const string what) { SendNotification("Dollar [" + ModeName(InpMode) + "]: " + what); }
string ModeName(const EDollarMode m)
  { return m==MODE_WATCH?"WATCH":m==MODE_SESSION?"SESSION":m==MODE_DEMO_HF?"DEMO_HF":"SIGNAL"; }

void ParityHeader()
  {
   if(FileIsExist(ParityFile(), FILE_COMMON)) return;
   const int fh = FileOpen(ParityFile(), FILE_WRITE | FILE_CSV | FILE_COMMON, ',');
   if(fh == INVALID_HANDLE) return;
   FileWrite(fh, "time", "mode", "symbol", "deal_type", "lots", "price", "profit");
   FileClose(fh);
  }

void OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &req,
                        const MqlTradeResult &res)
  {
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD || !HistoryDealSelect(trans.deal)) return;
   if(HistoryDealGetInteger(trans.deal, DEAL_MAGIC) != InpMagic) return;

   // event-sourced O(1) position counter (reconciled every 5s in housekeeping)
   const ENUM_DEAL_ENTRY entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
   if(entry == DEAL_ENTRY_IN)       { g_open_count++; g_acked++; }
   else if(entry == DEAL_ENTRY_OUT) { g_open_count = (int)MathMax(g_open_count - 1, 0); }

   // buffered journal: persistent handle, flushed on the 1s housekeeping tick
   if(g_journal_fh == INVALID_HANDLE) return;
   FileWrite(g_journal_fh, TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS),
             ModeName(InpMode),
             HistoryDealGetString(trans.deal, DEAL_SYMBOL),
             (string)HistoryDealGetInteger(trans.deal, DEAL_TYPE),
             DoubleToString(HistoryDealGetDouble(trans.deal, DEAL_VOLUME), 2),
             DoubleToString(HistoryDealGetDouble(trans.deal, DEAL_PRICE), _Digits),
             DoubleToString(HistoryDealGetDouble(trans.deal, DEAL_PROFIT), 2));
  }
