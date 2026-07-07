//+------------------------------------------------------------------+
//| SessionBreakout.mq5 — London-open breakout of the Asian range.   |
//|                                                                  |
//| MIRRORS hft/strategies/session_breakout.py. Candidate family,    |
//| NOT a validated edge: deploy to DEMO only after it passes the    |
//| harness gauntlet and the parity gate (design doc phase gates).   |
//|                                                                  |
//| CLOCK DISCIPLINE: all session logic runs in UTC because the      |
//| research data (Dukascopy) is UTC. Broker servers usually run     |
//| UTC+2/+3, so bar times are converted via the server-UTC offset   |
//| (auto-detected, or set InpServerUTCOffsetMinutes manually and    |
//| verify it in the log at init). The risk engine's DAY boundary    |
//| intentionally stays on SERVER time — confirm it matches the      |
//| firm's daily-reset clock when pinning the rulebook.              |
//|                                                                  |
//| Live-ops rules implemented here (design doc, Live operations):   |
//| - every position carries a server-side SL and TP from the        |
//|   moment it exists (set in the OrderSend itself)                 |
//| - no new entries while disconnected; open positions stay         |
//|   protected by their resting server-side stops                   |
//| - a risk breach liquidates our position immediately and halts    |
//|   the EA permanently (survives restarts via GlobalVariables)     |
//| - one-trade-per-day state survives restarts too                  |
//| - all closes are by ticket + magic, never by bare symbol         |
//| - heartbeat GlobalVariable + log; push notifications on          |
//|   fills, halts, and errors                                       |
//| - parity CSV trade log in the COMMON files folder                |
//+------------------------------------------------------------------+
#property copyright "HFT harness"
#property version   "1.20"
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

//--- clock (see header). Auto mode measures TimeCurrent()-TimeGMT() at init.
input bool   InpServerUTCOffsetAuto    = true;
input int    InpServerUTCOffsetMinutes = 0;  // used when auto=false

//--- strategy params (from walk-forward; frozen for demo). ALL HOURS ARE UTC.
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
int      g_srv_offset_sec = 0;  // server time minus UTC, seconds
double   g_asian_hi, g_asian_lo;
datetime g_day = 0;             // current UTC day
bool     g_traded_today = false;
datetime g_last_bar = 0;

string   TradedGV() { return "TD_" + (string)InpMagic; }
datetime UTCDay(const datetime t_utc) { return (datetime)(t_utc - (t_utc % 86400)); }

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
   if(_Symbol != "EURUSD")
      PrintFormat("SessionBreakout WARNING: params are EURUSD-frozen pips. On %s "
                  "the range filter (max %.0f pips = %.2f in price) will reject "
                  "most or all days — zero trades is the EXPECTED outcome, not a bug.",
                  _Symbol, InpMaxRangePips, InpMaxRangePips * g_pip);
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(20);

   // one clock: everything strategic is UTC; offset converts server-stamped bars
   if(InpServerUTCOffsetAuto)
     {
      const long raw = (long)TimeCurrent() - (long)TimeGMT();
      g_srv_offset_sec = (int)(MathRound(raw / 1800.0) * 1800);   // nearest 30 min
     }
   else
      g_srv_offset_sec = InpServerUTCOffsetMinutes * 60;
   PrintFormat("server-UTC offset: %+d minutes (%s) — VERIFY this matches the broker",
               g_srv_offset_sec / 60, InpServerUTCOffsetAuto ? "auto" : "manual");

   if(!risk.Init(InpInitialBalance, InpDailyLossFrac, InpTotalDDFrac,
                 InpRiskPerTrade, InpSafetyFactor, InpMaxLots,
                 "RISK_" + (string)InpMagic))
      return(INIT_FAILED);

   // restart re-sync: open position OR persisted traded-today marker
   g_day = UTCDay(TimeGMT());
   if(HasPosition())
     {
      g_traded_today = true;
      Print("re-sync: open position found, resuming management");
     }
   if(GlobalVariableCheck(TradedGV()) &&
      (datetime)GlobalVariableGet(TradedGV()) == g_day)
     {
      g_traded_today = true;
      Print("re-sync: already traded today (persisted marker)");
     }
   ParityLogHeader();
   Print("SessionBreakout initialized");
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   // risk mark runs on every tick; a breach liquidates immediately
   if(risk.OnTickUpdate())
     {
      CloseOurPositions("risk_breach");
      return;
     }

   // act once per closed M1 bar — decisions on closed bars only,
   // mirroring the Python engine's decide-on-close/fill-next-open rule
   const datetime bar_time = iTime(_Symbol, PERIOD_M1, 0);
   if(bar_time == g_last_bar)
      return;
   g_last_bar = bar_time;
   Heartbeat();

   // new UTC day: reset range state
   const datetime today = UTCDay(TimeGMT());
   if(today != g_day)
     {
      g_day = today;
      g_asian_hi = 0.0;
      g_asian_lo = 0.0;
      g_traded_today = false;
     }

   // last CLOSED bar, converted to UTC for all session decisions
   const double c_close = iClose(_Symbol, PERIOD_M1, 1);
   const double c_high  = iHigh(_Symbol, PERIOD_M1, 1);
   const double c_low   = iLow(_Symbol, PERIOD_M1, 1);
   const datetime bar_utc = iTime(_Symbol, PERIOD_M1, 1) - g_srv_offset_sec;
   MqlDateTime bt;
   TimeToStruct(bar_utc, bt);

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
      CloseOurPositions("time_stop");
      return;
     }

   if(risk.Halted() || HasPosition() || g_traded_today)
      return;
   if(g_asian_hi == 0.0 || g_asian_lo == 0.0)
      return;
   if(bt.hour < InpAsianEndHour || bt.hour >= InpLondonEndHour)
      return;

   // never open new positions while disconnected (design doc policy)
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
         MarkTradedToday(StringFormat("SB long %.2f lots, sl=%.1fp tp=%.1fp",
                                      lots, sl_pips, tp_pips));
     }
   else if(c_close < g_asian_lo)
     {
      const double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      if(trade.Sell(lots, _Symbol, 0.0,
                    bid + sl_pips * g_pip, bid - tp_pips * g_pip, "sb_short"))
         MarkTradedToday(StringFormat("SB short %.2f lots, sl=%.1fp tp=%.1fp",
                                      lots, sl_pips, tp_pips));
     }
  }

//+------------------------------------------------------------------+
//| Parity CSV: one row per closed deal, diffed against the Python   |
//| harness trade log by scripts/parity_check.py.                    |
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

//--- close ONLY our positions, by ticket + magic — never by bare symbol
void CloseOurPositions(const string reason)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      const ulong ticket = PositionGetTicket(i);
      if(PositionSelectByTicket(ticket) &&
         PositionGetInteger(POSITION_MAGIC) == InpMagic &&
         PositionGetString(POSITION_SYMBOL) == _Symbol)
        {
         if(!trade.PositionClose(ticket))
            Notify(StringFormat("close FAILED (%s) ticket=%I64u err=%d",
                                reason, ticket, GetLastError()));
         else
            Notify(StringFormat("closed ticket=%I64u (%s)", ticket, reason));
        }
     }
  }

void MarkTradedToday(const string msg)
  {
   g_traded_today = true;
   GlobalVariableSet(TradedGV(), (double)g_day);  // survives restarts
   Notify(msg);
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

void Heartbeat()
  {
   GlobalVariableSet("HB_" + (string)InpMagic, (double)TimeCurrent());
   if(TimeCurrent() % 900 < 60)  // roughly one log line per 15 minutes
      PrintFormat("heartbeat: equity=%.2f halted=%d",
                  AccountInfoDouble(ACCOUNT_EQUITY), risk.Halted());
  }

void Notify(const string msg)
  {
   Print(msg);
   SendNotification(msg);
  }
