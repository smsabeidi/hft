//+------------------------------------------------------------------+
//| RiskEngine.mqh — prop-firm risk engine, MQL5 side.               |
//|                                                                  |
//| MIRRORS hft/risk/engine.py method-for-method. The parity gate    |
//| (scripts/parity_check.py) diffs decisions between the two        |
//| implementations on identical data. If you change semantics here, |
//| change the Python reference FIRST, then re-run parity.           |
//|                                                                  |
//| Semantics:                                                       |
//| - daily loss floor  = day_anchor - daily_frac * initial_balance  |
//|   (day anchor = max(balance, equity) at server-day rollover;     |
//|   CONFIRM the firm's dashboard resets at server midnight when    |
//|   pinning the rulebook — FTMO uses CE(S)T, which matches the     |
//|   server clock of most FTMO-feed brokers)                        |
//| - total dd floor    = initial_balance * (1 - total_frac)         |
//| - a BREACH permanently halts the EA — it survives restarts,      |
//|   redeploys, and new days. Account death is not day-scoped.      |
//| - BLOCKING (AllowedLots -> 0) is normal operation, not failure   |
//| - sizing: worst-case loss = stop distance x safety factor (the   |
//|   factor sized to also absorb spread/slippage/commission), must  |
//|   fit inside remaining daily AND total headroom                  |
//+------------------------------------------------------------------+
#property copyright "HFT harness"
#property strict

class CRiskEngine
  {
private:
   double            m_initial_balance;
   double            m_day_anchor;
   double            m_daily_frac;
   double            m_total_frac;
   double            m_risk_frac;
   double            m_safety_factor;
   double            m_max_lots;
   bool              m_halted;
   datetime          m_day_start;      // start of current server day
   string            m_gv;             // GlobalVariable name prefix

   datetime          DayOf(datetime t) const { return (datetime)(t - (t % 86400)); }

   void              Persist()
     {
      GlobalVariableSet(m_gv + "_anchor", m_day_anchor);
      GlobalVariableSet(m_gv + "_day", (double)m_day_start);
      GlobalVariableSet(m_gv + "_halted", m_halted ? 1.0 : 0.0);
     }

public:
   bool              Init(const double initial_balance,
                          const double daily_frac,
                          const double total_frac,
                          const double risk_frac,
                          const double safety_factor,
                          const double max_lots,
                          const string gv_prefix)
     {
      if(initial_balance <= 0 || daily_frac <= 0 || total_frac <= 0)
         return(false);
      m_initial_balance = initial_balance;
      m_daily_frac      = daily_frac;
      m_total_frac      = total_frac;
      m_risk_frac       = risk_frac;
      m_safety_factor   = safety_factor;
      m_max_lots        = max_lots;
      m_gv              = gv_prefix;

      // a halt is PERMANENT: restore it regardless of what day it is
      m_halted = GlobalVariableCheck(m_gv + "_halted") &&
                 GlobalVariableGet(m_gv + "_halted") > 0.5;

      // the day anchor is day-scoped: restore only within the same server day
      if(GlobalVariableCheck(m_gv + "_day") &&
         (datetime)GlobalVariableGet(m_gv + "_day") == DayOf(TimeCurrent()))
        {
         m_day_anchor = GlobalVariableGet(m_gv + "_anchor");
         m_day_start  = (datetime)GlobalVariableGet(m_gv + "_day");
         PrintFormat("RiskEngine: re-synced (anchor=%.2f halted=%d)",
                     m_day_anchor, m_halted);
        }
      else
        {
         m_day_anchor = MathMax(AccountInfoDouble(ACCOUNT_BALANCE),
                                AccountInfoDouble(ACCOUNT_EQUITY));
         m_day_start  = DayOf(TimeCurrent());
        }
      if(m_halted)
         Print("RiskEngine: account is BREACHED (persisted state). Trading stays halted.");
      Persist();
      return(true);
     }

   double            DailyLossFloor()  const { return m_day_anchor - m_daily_frac * m_initial_balance; }
   double            TotalDDFloor()    const { return m_initial_balance * (1.0 - m_total_frac); }
   bool              Halted()          const { return m_halted; }

   //--- call on every tick; returns true when a breach JUST happened -------
   bool              OnTickUpdate()
     {
      const datetime today = DayOf(TimeCurrent());
      if(today != m_day_start)
        {
         m_day_start  = today;
         m_day_anchor = MathMax(AccountInfoDouble(ACCOUNT_BALANCE),
                                AccountInfoDouble(ACCOUNT_EQUITY));
         Persist();
        }
      return(MarkEquity(AccountInfoDouble(ACCOUNT_EQUITY)));
     }

   //--- returns true when a breach just happened ---------------------------
   bool              MarkEquity(const double equity)
     {
      if(m_halted)
         return(false);
      string kind = "";
      if(equity <= DailyLossFloor())
         kind = "daily_loss";
      else if(equity <= TotalDDFloor())
         kind = "total_drawdown";
      if(kind == "")
         return(false);
      m_halted = true;
      Persist();
      const string msg = StringFormat(
         "RISK BREACH (%s): equity %.2f <= floor. EA halted permanently.",
         kind, equity);
      Print(msg);
      SendNotification(msg);   // push to phone (enable in terminal settings)
      return(true);
     }

   //--- position sizing; 0.0 means DO NOT TRADE ----------------------------
   double            AllowedLots(const double stop_pips,
                                 const double equity,
                                 const double pip_value_per_lot)
     {
      if(m_halted || stop_pips <= 0.0 || pip_value_per_lot <= 0.0)
         return(0.0);

      double lots = (m_risk_frac * equity) / (stop_pips * pip_value_per_lot);

      const double headroom = MathMin(equity - DailyLossFloor(),
                                      equity - TotalDDFloor());
      if(headroom <= 0.0)
         return(0.0);
      const double worst_per_lot = stop_pips * pip_value_per_lot * m_safety_factor;
      lots = MathMin(lots, headroom / worst_per_lot);
      lots = MathMin(lots, m_max_lots);

      const double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
      const double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
      const double vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
      // floor to the step, NEVER round up (rounding up = more risk than sized).
      // the 1e-9 guards against FP dust pushing a whole step down; the final
      // NormalizeDouble(_, 8) only strips representation noise, it cannot
      // cross a 0.001-or-coarser volume step.
      if(step > 0.0)
         lots = MathFloor(lots / step + 1e-9) * step;
      lots = MathMin(lots, vmax);
      if(lots < vmin)
         return(0.0);
      return(NormalizeDouble(lots, 8));
     }
  };
