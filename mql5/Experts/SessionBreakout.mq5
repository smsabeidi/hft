//+------------------------------------------------------------------+
//| SessionBreakout.mq5 — London-open breakout of the Asian range.   |
//|                                                                  |
//| MIRRORS hft/strategies/session_breakout.py. Candidate family,    |
//| NOT a validated edge: deploy to DEMO only after it passes the    |
//| harness gauntlet and the parity gate (design doc phase gates).   |
//|                                                                  |
//| Live-ops rules implemented here (design doc, Live operations):   |
//| - every position carries a server-side SL and TP from the        |
//|   moment it exists (set in the OrderSend itself)                 |
//| - no new entries while disconnected; open positions stay         |
//|   protected by their resting server-side stops                   |
//| - state re-sync from open positions on restart (by magic)        |
//| - heartbeat log line + GlobalVariable timestamp every bar        |
//| - push notifications on fills, halts, and errors                 |
//| - parity CSV trade log in the COMMON files folder                |
//+------------------------------------------------------------------+
#property copyright "HFT harness"
#property version   "0.10"
#property strict

#include <Trade\Trade.mqh>
#include <RiskEngine.mqh>

//--- firm config (frozen at deploy; NEVER optimized — design doc, Compliance)
input double InpInitialBalance   = 50000.0; // evaluation starting balance
input double InpDailyLossFrac    = 0.05;    // firm daily loss limit
input double InpTotalDDFrac      = 0.10;    // firm total drawdown limit
input double InpRiskPerTrade     = 0.005;   // own policy: risk per trade
input double InpSafetyFactor     = 2.0;     // own policy: headroom safety
input double InpMaxLots          = 5.0;     // firm max lots
input bool   InpRulesVerified    = false;   // set true ONLY after pinning the firm rulebook

//--- strategy params (from walk-forward; frozen for demo)
input int    InpAsianStartHour   = 0;       // UTC
input int    InpAsianEndHour     = 7;       // UTC
input int    InpLondonEndHour    = 12;      // UTC
input int    InpSessionEndHour   = 16;      // UTC time-stop
input double InpKTakeProfit      = 1.5;     // TP = k x range
input double InpMinSlPips        = 8.0;
input double InpMaxSlPips        = 30.0;
input double InpMaxRangePips     = 40.0;

input long   InpMagic            = 20260706;
input string InpParityLog        = "parity_session_breakout.csv";

CTrade      trade;
CRiskEngine risk;

double   g_pip;                 // pip size in price units (10 * _Point on 5-digit)
double   g_asian_hi, g_asian_lo;
datetime g_day = 0;
bool     g_traded_today = false;
datetime g_last_bar = 0;

//+------------------------------------------------------------------+
int OnInit()
  {
   if(!InpRulesVerified)
     {
      // The config gate from the design doc: no demo/live run before the
      // rulebook is pinned. Backtests in the Strategy Tester are allowed.
      if(!MQLInfoInteger(MQL_TESTER))
        {
         Alert("RiskEngine: firm rules not verified (InpRulesVerified=false). ",
               "Pin the rulebook, set the inputs, and redeploy. EA will not trade.");
         return(INIT_FAILED);
        }
     }

   g_pip = (_Digits == 5 || _Digits == 3) ? 10.0 * _Point : _Point;
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(20);

   if(!risk.Init(InpInitialBalance, InpDailyLossFrac, InpTotalDDFrac,
                 InpRiskPerTrade, InpSafetyFactor, InpMaxLots,
                 "RISK_" + (string)InpMagic))
      return(INIT_FAILED);

   // restart re-sync: an open position of ours means mid-trade restart
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      const ulong ticket = PositionGetTicket(i);
      if(PositionSelectByTicket(ticket) &&
         PositionGetInteger(POSITION_MAGIC) == InpMagic &&
         PositionGetString(POSITION_SYMBOL) == _Symbol)
        {
         g_traded_today = true;
         PrintFormat("re-sync: found open position #%I64u, resuming management", ticket);
        }
     }
   ParityLogHeader();
   Print("SessionBreakout initialized");
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   risk.OnTickUpdate();

   // act once per closed M1 bar — decisions on closed bars only,
   // mirroring the Python engine's decide-on-close/fill-next-open rule
   const datetime bar_time = iTime(_Symbol, PERIOD_M1, 0);
   if(bar_time == g_last_bar)
      return;
   g_last_bar = bar_time;
   Heartbeat(bar_time);

   const MqlDateTime now = TimeToStruct_(TimeGMT());

   // new day: reset range state
   const datetime today = (datetime)(TimeGMT() - (TimeGMT() % 86400));
   if(today != g_day)
     {
      g_day = today;
      g_asian_hi = 0.0;
      g_asian_lo = 0.0;
      g_traded_today = false;
     }

   // use the last CLOSED bar for all decisions
   const double c_close = iClose(_Symbol, PERIOD_M1, 1);
   const double c_high  = iHigh(_Symbol, PERIOD_M1, 1);
   const double c_low   = iLow(_Symbol, PERIOD_M1, 1);
   const MqlDateTime bt = TimeToStruct_(iTime(_Symbol, PERIOD_M1, 1));

   // Asian session: build the range
   if(bt.hour >= InpAsianStartHour && bt.hour < InpAsianEndHour)
     {
      if(g_asian_hi == 0.0 || c_high > g_asian_hi) g_asian_hi = c_high;
      if(g_asian_lo == 0.0 || c_low  < g_asian_lo) g_asian_lo = c_low;
      return;
     }

   // time-stop
   if(HasPosition() && bt.hour >= InpSessionEndHour)
     {
      trade.PositionClose(_Symbol);
      return;
     }

   if(risk.Halted() || HasPosition() || g_traded_today)
      return;
   if(g_asian_hi == 0.0 || g_asian_lo == 0.0)
      return;
   if(bt.hour < InpAsianEndHour || bt.hour >= InpLondonEndHour)
      return;

   // never trade while disconnected (design doc disconnect policy)
   if(!TerminalInfoInteger(TERMINAL_CONNECTED))
      return;

   const double range_pips = (g_asian_hi - g_asian_lo) / g_pip;
   if(range_pips <= 0.0 || range_pips > InpMaxRangePips)
      return;

   const double sl_pips = MathMin(MathMax(range_pips, InpMinSlPips), InpMaxSlPips);
   const double tp_pips = InpKTakeProfit * range_pips;
   const double pip_value_per_lot =
      SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE) *
      (g_pip / SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE));
   const double lots = risk.AllowedLots(sl_pips, AccountInfoDouble(ACCOUNT_EQUITY),
                                        pip_value_per_lot);
   if(lots <= 0.0)
      return;

   if(c_close > g_asian_hi)
     {
      const double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      // SL/TP travel inside the OrderSend — the position is never naked
      if(trade.Buy(lots, _Symbol, 0.0,
                   ask - sl_pips * g_pip, ask + tp_pips * g_pip, "sb_long"))
        {
         g_traded_today = true;
         Notify(StringFormat("SB long %.2f lots, sl=%.1fp tp=%.1fp", lots, sl_pips, tp_pips));
        }
     }
   else if(c_close < g_asian_lo)
     {
      const double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      if(trade.Sell(lots, _Symbol, 0.0,
                    bid + sl_pips * g_pip, bid - tp_pips * g_pip, "sb_short"))
        {
         g_traded_today = true;
         Notify(StringFormat("SB short %.2f lots, sl=%.1fp tp=%.1fp", lots, sl_pips, tp_pips));
        }
     }
  }

//+------------------------------------------------------------------+
//| Parity CSV: one row per closed deal, diffed against the Python   |
//| harness trade log by the parity gate.                            |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
  {
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD)
      return;
   if(!HistoryDealSelect(trans.deal))
      return;
   if(HistoryDealGetInteger(trans.deal, DEAL_MAGIC) != InpMagic)
      return;
   const int fh = FileOpen(InpParityLog,
                           FILE_READ | FILE_WRITE | FILE_CSV | FILE_COMMON, ',');
   if(fh == INVALID_HANDLE)
      return;
   FileSeek(fh, 0, SEEK_END);
   FileWrite(fh,
             TimeToString(HistoryDealGetInteger(trans.deal, DEAL_TIME),
                          TIME_DATE | TIME_SECONDS),
             HistoryDealGetString(trans.deal, DEAL_SYMBOL),
             (string)HistoryDealGetInteger(trans.deal, DEAL_TYPE),
             DoubleToString(HistoryDealGetDouble(trans.deal, DEAL_VOLUME), 2),
             DoubleToString(HistoryDealGetDouble(trans.deal, DEAL_PRICE), _Digits),
             DoubleToString(HistoryDealGetDouble(trans.deal, DEAL_COMMISSION), 2),
             DoubleToString(HistoryDealGetDouble(trans.deal, DEAL_SWAP), 2),
             DoubleToString(HistoryDealGetDouble(trans.deal, DEAL_PROFIT), 2));
   FileClose(fh);
  }

//+------------------------------------------------------------------+
bool HasPosition()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      const ulong ticket = PositionGetTicket(i);
      if(PositionSelectByTicket(ticket) &&
         PositionGetInteger(POSITION_MAGIC) == InpMagic &&
         PositionGetString(POSITION_SYMBOL) == _Symbol)
         return(true);
     }
   return(false);
  }

void ParityLogHeader()
  {
   if(FileIsExist(InpParityLog, FILE_COMMON))
      return;
   const int fh = FileOpen(InpParityLog, FILE_WRITE | FILE_CSV | FILE_COMMON, ',');
   if(fh == INVALID_HANDLE)
      return;
   FileWrite(fh, "time", "symbol", "deal_type", "lots", "price",
             "commission", "swap", "profit");
   FileClose(fh);
  }

void Heartbeat(const datetime t)
  {
   GlobalVariableSet("HB_" + (string)InpMagic, (double)TimeCurrent());
   if(t % 900 == 0)  // one log line per 15 minutes
      PrintFormat("heartbeat: equity=%.2f halted=%d",
                  AccountInfoDouble(ACCOUNT_EQUITY), risk.Halted());
  }

void Notify(const string msg)
  {
   Print(msg);
   SendNotification(msg);
  }

MqlDateTime TimeToStruct_(const datetime t)
  {
   MqlDateTime s;
   TimeToStruct(t, s);
   return(s);
  }
