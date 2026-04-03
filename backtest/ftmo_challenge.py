"""
FTMO 2-step challenge hints from backtest result (simplified).
"""

from __future__ import annotations

from typing import Any

from backtest.result import BacktestResult


def simulate_two_step_challenge(
    result: BacktestResult,
    initial_balance: float,
    phase1_target_pct: float = 0.10,
    phase2_target_pct: float = 0.05,
    min_trading_days: int = 4,
) -> dict[str, Any]:
    """
    Heuristic: cumulative profit vs static targets; trading days = unique entry days.
    """
    delta = result.final_balance - initial_balance
    days = {t.entry_time.strftime("%Y-%m-%d") for t in result.trades}
    n_days = len(days)
    p1 = initial_balance * phase1_target_pct
    p2 = initial_balance * phase2_target_pct
    pass_p1 = delta >= p1 and n_days >= min_trading_days
    pass_p2 = delta >= p1 + p2 and n_days >= min_trading_days
    phase = "funded" if pass_p2 else ("phase2" if pass_p1 else "phase1")

    return {
        "final_phase": phase,
        "profit_usd": delta,
        "phase1_target_usd": p1,
        "phase2_extra_target_usd": p2,
        "trading_days": n_days,
        "pass_phase1_profit_rule": pass_p1,
        "pass_phase2_profit_rule": pass_p2,
        "note": "Simplified; real FTMO uses MetriX + calendar. Use ftmo_compliant for hard limits.",
    }


def check_ftmo_compliance(
    result: BacktestResult,
    initial_balance: float,
    max_daily_loss_pct: float = 0.05,
    max_overall_loss_pct: float = 0.10,
    best_day_max_pct: float = 0.50,
) -> tuple[bool, str]:
    """Post-hoc rules on aggregated backtest stats."""
    if result.max_drawdown_pct > max_overall_loss_pct * 100 + 1e-6:
        return False, f"Max DD {result.max_drawdown_pct:.1f}% > {max_overall_loss_pct*100:.0f}%"

    if result.max_daily_loss_pct > max_daily_loss_pct * 100 + 1e-6:
        return False, f"Max daily loss {result.max_daily_loss_pct:.1f}% > {max_daily_loss_pct*100:.0f}%"

    total_pos = sum(v for v in result.daily_pnls.values() if v > 0)
    if total_pos > 0 and result.best_day_profit / total_pos >= best_day_max_pct:
        return False, f"Best day {result.best_day_profit/total_pos:.0%} of +daily sum (limit {best_day_max_pct:.0%})"

    return True, ""
