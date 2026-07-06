# HFT — MT5 Prop-Firm Algorithmic Trading System

Design doc lives at `~/.gstack/projects/HFT/` (written by /office-hours). Read it before planning or building anything.

Ground rules for this project:
- Success metrics are after-cost expectancy, Sharpe, and max drawdown. Win rate is a diagnostic, never a target.
- No live capital until a strategy survives: realistic-cost backtest → walk-forward → 30+ days demo with matching stats.
- Prop-firm drawdown limits are hard constants in the risk engine, not tunable parameters.

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
- Author a backlog-ready spec/issue → invoke /spec
