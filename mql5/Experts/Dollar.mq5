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
//--- session mode (UTC) ---
input int         InpAsianEndHour   = 7;
input int         InpLondonEndHour  = 12;
input double      InpKTakeProfit    = 1.5;
input double      InpMinSlPips      = 8.0;
input double      InpMaxSlPips      = 30.0;
input double      InpMaxRangePips   = 40.0;
input int         InpMaxSpreadPts   = 12;
//--- demo-HF mode ---
input double      InpHFTakeProfit   = 10.0;
input double      InpHFStopLoss     = 60.0;
input int         InpHFEverySeconds = 60;
input int         InpHFMaxOpen      = 5;
input double      InpHFLots         = 1.0;
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
   if(HasOurPosition())
      g_traded_today = true;
   ParityHeader();

   if(InpMode == MODE_DEMO_HF)
      EventSetTimer(MathMax(InpHFEverySeconds, 5));
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

void OnDeinit(const int reason) { EventKillTimer(); }

//+------------------------------------------------------------------+
void OnTick()
  {
   if(risk.OnTickUpdate())          // breach: flatten ours, halt forever
      CloseOurPositions();
  }

//+------------------------------------------------------------------+
void OnTimer()
  {
   if(risk.Halted())
      return;
   Heartbeat();
   if(!(bool)TerminalInfoInteger(TERMINAL_CONNECTED))
      return;                       // no new entries while disconnected

   switch(InpMode)
     {
      case MODE_WATCH:    return;                 // telemetry only
      case MODE_SESSION:  ManageSession();  break;
      case MODE_DEMO_HF:  ManageDemoHF();   break;
      case MODE_SIGNAL:   ManageSignal();   break;
     }
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
void ManageDemoHF()
  {
   // fixed InpHFLots BY DESIGN: this is a geometry demonstration, not a
   // risk-sized strategy — constant size is what makes the win-rate dial
   // legible. Demo-only guard (OnInit) is why bypassing the throttle is safe.
   if(OurOpenCount() >= (int)MathMax(MathMin(InpHFMaxOpen, 20), 1)) return;
   const double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   const double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(ask <= 0 || bid <= 0) return;
   const double tp = InpHFTakeProfit * g_pip, sl = InpHFStopLoss * g_pip;
   if(g_hf_dir > 0) trade.Buy(InpHFLots, _Symbol, 0.0, bid - sl, ask + tp, "Dollar HF");
   else             trade.Sell(InpHFLots, _Symbol, 0.0, ask + sl, bid - tp, "Dollar HF");
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

int OurOpenCount()
  {
   int n = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      const ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpMagic) n++;
     }
   return(n);
  }

bool HasOurPosition() { return OurOpenCount() > 0; }

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
   const int fh = FileOpen(ParityFile(), FILE_READ | FILE_WRITE | FILE_CSV | FILE_COMMON, ',');
   if(fh == INVALID_HANDLE) return;
   FileSeek(fh, 0, SEEK_END);
   FileWrite(fh, TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS), ModeName(InpMode),
             HistoryDealGetString(trans.deal, DEAL_SYMBOL),
             (string)HistoryDealGetInteger(trans.deal, DEAL_TYPE),
             DoubleToString(HistoryDealGetDouble(trans.deal, DEAL_VOLUME), 2),
             DoubleToString(HistoryDealGetDouble(trans.deal, DEAL_PRICE), _Digits),
             DoubleToString(HistoryDealGetDouble(trans.deal, DEAL_PROFIT), 2));
   FileClose(fh);
  }
