"""
Chỉ số mở rộng: Expectancy, Sharpe gần đúng (từ daily PnL).

Expectancy (USD/trade, sau cost):
  E ≈ (WinRate × AvgWin) − (LossRate × |AvgLoss|)
"""

from __future__ import annotations

import math

from backtest.result import BacktestResult


def expectancy_usd_per_trade(result: BacktestResult) -> float:
    """
    Kỳ vọng lợi nhuận mỗi lệnh ($). Trùng với mean(pnl) khi định nghĩa avg win/loss đúng.
    """
    if not result.trades:
        return 0.0
    wins = [t.pnl for t in result.trades if t.pnl > 0]
    losses = [t.pnl for t in result.trades if t.pnl < 0]
    n = len(result.trades)
    wr = len(wins) / n
    lr = len(losses) / n
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
    return wr * avg_win - lr * avg_loss


def sharpe_from_daily_returns(
    result: BacktestResult,
    *,
    periods_per_year: float = 252.0,
) -> float | None:
    """
    Sharpe gần đúng: return ngày = pnl_ngày / equity đầu ngày; mean/std * sqrt(252).
    """
    if not result.daily_pnls or result.initial_balance <= 0:
        return None
    bal = result.initial_balance
    rets: list[float] = []
    for _day, pnl in sorted(result.daily_pnls.items()):
        r = pnl / bal if bal else 0.0
        rets.append(r)
        bal = bal + pnl
    if len(rets) < 2:
        return None
    mean_r = sum(rets) / len(rets)
    var = sum((x - mean_r) ** 2 for x in rets) / (len(rets) - 1)
    std = math.sqrt(var) if var > 0 else 0.0
    if std < 1e-12:
        return None
    return (mean_r / std) * math.sqrt(periods_per_year)


def extended_metrics_summary(result: BacktestResult) -> dict[str, float | None]:
    """Dict cho reporter / log."""
    exp = expectancy_usd_per_trade(result)
    sh = sharpe_from_daily_returns(result)
    return {
        "expectancy_usd_per_trade": exp,
        "sharpe_ratio_approx": sh,
    }
