"""Backtest result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SimulatedTrade:
    """Single simulated trade from backtest."""

    symbol: str
    direction: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float
    outcome: str  # "win" | "loss" | "timeout"
    rr: float


@dataclass
class BacktestResult:
    """Aggregated backtest output."""

    symbol: str
    start: datetime
    end: datetime
    initial_balance: float
    final_balance: float
    total_return_pct: float
    trades: list[SimulatedTrade] = field(default_factory=list)
    equity_curve: list[tuple[datetime, float]] = field(default_factory=list)
    daily_pnls: dict[str, float] = field(default_factory=dict)
    max_drawdown_pct: float = 0.0
    max_daily_loss_pct: float = 0.0
    best_day_profit: float = 0.0
    best_day_ratio: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    ftmo_compliant: bool = True
    ftmo_fail_reason: str = ""
    challenge: dict[str, Any] = field(default_factory=dict)
