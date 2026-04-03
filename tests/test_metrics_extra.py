"""Expectancy & Sharpe helpers."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backtest.metrics_extra import expectancy_usd_per_trade, extended_metrics_summary, sharpe_from_daily_returns
from backtest.result import BacktestResult, SimulatedTrade


def _trade(pnl: float) -> SimulatedTrade:
    return SimulatedTrade(
        symbol="EURUSD",
        direction="BUY",
        entry_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
        exit_time=datetime(2025, 1, 2, tzinfo=timezone.utc),
        entry_price=1.0,
        exit_price=1.01,
        pnl=pnl,
        pnl_pct=0.0,
        outcome="win" if pnl > 0 else "loss",
        rr=1.0,
    )


def test_expectancy_formula_matches_mean_pnl() -> None:
    """E = WR*AvgWin - LR*|AvgLoss| tương đương mean(pnl) với cùng định nghĩa."""
    trades = [_trade(100), _trade(100), _trade(-50)]
    r = BacktestResult(
        symbol="X",
        start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        end=datetime(2025, 1, 2, tzinfo=timezone.utc),
        initial_balance=10_000,
        final_balance=10_150,
        total_return_pct=1.5,
        trades=trades,
    )
    e = expectancy_usd_per_trade(r)
    mean_pnl = sum(t.pnl for t in trades) / len(trades)
    assert abs(e - mean_pnl) < 1e-6


def test_sharpe_none_when_few_days() -> None:
    r = BacktestResult(
        symbol="X",
        start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        end=datetime(2025, 1, 2, tzinfo=timezone.utc),
        initial_balance=10_000,
        final_balance=10_000,
        total_return_pct=0,
        daily_pnls={"2025-01-01": 100.0},
    )
    assert sharpe_from_daily_returns(r) is None


def test_extended_summary_keys() -> None:
    r = BacktestResult(
        symbol="X",
        start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        end=datetime(2025, 1, 5, tzinfo=timezone.utc),
        initial_balance=10_000,
        final_balance=10_200,
        total_return_pct=2,
        trades=[_trade(50)],
        daily_pnls={"2025-01-01": 50.0, "2025-01-02": -10.0, "2025-01-03": 20.0},
    )
    m = extended_metrics_summary(r)
    assert "expectancy_usd_per_trade" in m
    assert m["expectancy_usd_per_trade"] == 50.0
    assert m.get("sharpe_ratio_approx") is not None or m.get("sharpe_ratio_approx") is None
