"""
Backtest engine — walk-forward SMC signals + simplified fill model + FTMO metrics.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
from loguru import logger

from backtest.data_loader import build_multi_timeframe
from backtest.ftmo_challenge import check_ftmo_compliance, simulate_two_step_challenge
from backtest.result import BacktestResult, SimulatedTrade
from src.strategy.smc_engine import SMCEngine


def _ensure_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _simulate_exit(
    m15: pd.DataFrame,
    start_idx: int,
    direction: str,
    entry: float,
    sl: float,
    tp: float,
    max_bars: int = 96,
) -> tuple[str, int, float, float]:
    """
    Conservative bar rule: if SL and TP both touched same bar, SL first.
    Returns (outcome, exit_bar_index, exit_price).
    """
    end = min(start_idx + max_bars, len(m15))
    for j in range(start_idx, end):
        row = m15.iloc[j]
        lo = float(row["low"])
        hi = float(row["high"])
        cl = float(row["close"])
        if direction == "BUY":
            if lo <= sl:
                return "loss", j, sl
            if hi >= tp:
                return "win", j, tp
        else:
            if hi >= sl:
                return "loss", j, sl
            if lo <= tp:
                return "win", j, tp
    last = m15.iloc[end - 1]
    return "timeout", end - 1, float(last["close"])


class BacktestEngine:
    """Run SMC backtest on OHLCV (M15 base → H1/H4 resampled)."""

    def __init__(self, settings: dict, symbols_specs: dict[str, dict[str, Any]]):
        self._settings = settings
        strategy = dict(settings.get("strategy", {}))
        self._risk_pct = float(settings.get("risk", {}).get("risk_per_trade", 0.01))
        self._smc = SMCEngine(strategy, symbols_specs)

    def run(
        self,
        symbol: str,
        m15: pd.DataFrame,
        *,
        initial_balance: float = 10_000.0,
        step_bars: int = 4,
        min_m15_bars: int = 120,
        cooldown_bars: int = 8,
    ) -> BacktestResult:
        """
        Walk forward on M15; resample H1/H4 internally.

        Args:
            symbol: e.g. EURUSD
            m15: DataFrame with time, open, high, low, close (UTC)
            initial_balance: starting equity
            step_bars: only run SMC every N M15 bars (perf)
            min_m15_bars: minimum history before first signal
        """
        m15 = m15.sort_values("time").reset_index(drop=True)
        if len(m15) < min_m15_bars:
            raise ValueError(f"Need at least {min_m15_bars} M15 bars")

        frames = build_multi_timeframe(m15)
        m15 = frames["M15"]
        h1 = frames["H1"]
        h4 = frames["H4"]

        equity = initial_balance
        equity_curve: list[tuple[datetime, float]] = [(m15.iloc[min_m15_bars]["time"], equity)]
        trades: list[SimulatedTrade] = []
        daily_pnls: dict[str, float] = {}
        min_equity = equity
        max_daily_loss_pct = 0.0

        last_signal_key: str | None = None
        next_allowed_i = 0

        for i in range(min_m15_bars, len(m15) - 1, step_bars):
            if i < next_allowed_i:
                continue

            t = m15.iloc[i]["time"]
            t = _ensure_utc(pd.Timestamp(t).to_pydatetime())

            d_m15 = m15[m15["time"] <= t]
            d_h1 = h1[h1["time"] <= t]
            d_h4 = h4[h4["time"] <= t]
            if len(d_m15) < 50 or len(d_h1) < 20 or len(d_h4) < 10:
                continue

            data = {"H4": d_h4, "H1": d_h1, "M15": d_m15}
            try:
                sigs = self._smc.analyze(symbol, data)
            except Exception as e:
                logger.debug("SMC skip @{}: {}", i, e)
                continue

            if not sigs:
                continue

            sig = sigs[0]
            key = f"{sig.direction.value}_{sig.entry_price:.5f}"
            if key == last_signal_key:
                continue
            last_signal_key = key

            direction = "BUY" if sig.direction.value == "BUY" else "SELL"
            entry = float(sig.entry_price)
            sl = float(sig.stop_loss)
            tp = float(sig.take_profit_1)

            outcome, exit_j, exit_px = _simulate_exit(m15, i + 1, direction, entry, sl, tp)

            risk = equity * self._risk_pct
            sl_dist = abs(entry - sl)
            if sl_dist < 1e-12:
                continue
            rr = abs(tp - entry) / sl_dist

            if outcome == "win":
                pnl = risk * rr
            elif outcome == "loss":
                pnl = -risk
            else:
                move = (exit_px - entry) if direction == "BUY" else (entry - exit_px)
                pnl = risk * (move / sl_dist) if sl_dist else 0.0

            equity += pnl
            min_equity = min(min_equity, equity)
            exit_t = m15.iloc[exit_j]["time"]
            exit_t = _ensure_utc(pd.Timestamp(exit_t).to_pydatetime())

            day = exit_t.strftime("%Y-%m-%d")
            daily_pnls[day] = daily_pnls.get(day, 0.0) + pnl

            dloss = daily_pnls[day] / initial_balance * 100
            if daily_pnls[day] < 0:
                max_daily_loss_pct = max(max_daily_loss_pct, abs(dloss))

            equity_curve.append((exit_t, equity))

            pnl_pct = (pnl / initial_balance) * 100 if initial_balance else 0.0
            trades.append(
                SimulatedTrade(
                    symbol=symbol,
                    direction=direction,
                    entry_time=t,
                    exit_time=exit_t,
                    entry_price=entry,
                    exit_price=exit_px,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    outcome=outcome,
                    rr=rr,
                )
            )

            next_allowed_i = exit_j + cooldown_bars

        max_dd_pct = (initial_balance - min_equity) / initial_balance * 100 if initial_balance else 0.0

        wins = [t for t in trades if t.outcome == "win"]
        losses = [t for t in trades if t.outcome == "loss"]
        total_trades = len(trades)
        win_rate = len(wins) / total_trades if total_trades else 0.0
        gross_win = sum(t.pnl for t in trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))
        if gross_loss > 1e-9:
            profit_factor = gross_win / gross_loss
        else:
            profit_factor = 99.99 if gross_win > 0 else 0.0

        pos_days = {k: v for k, v in daily_pnls.items() if v > 0}
        best_day_profit = max(pos_days.values()) if pos_days else 0.0
        total_pos = sum(pos_days.values())
        best_day_ratio = (best_day_profit / total_pos) if total_pos > 0 else 0.0

        final_balance = equity
        total_return = (final_balance - initial_balance) / initial_balance * 100 if initial_balance else 0.0

        result = BacktestResult(
            symbol=symbol,
            start=_ensure_utc(pd.Timestamp(m15.iloc[0]["time"]).to_pydatetime()),
            end=_ensure_utc(pd.Timestamp(m15.iloc[-1]["time"]).to_pydatetime()),
            initial_balance=initial_balance,
            final_balance=final_balance,
            total_return_pct=total_return,
            trades=trades,
            equity_curve=equity_curve,
            daily_pnls=daily_pnls,
            max_drawdown_pct=max_dd_pct,
            max_daily_loss_pct=max_daily_loss_pct,
            best_day_profit=best_day_profit,
            best_day_ratio=best_day_ratio,
            win_rate=win_rate,
            profit_factor=profit_factor if profit_factor != float("inf") else 0.0,
            total_trades=total_trades,
            wins=len(wins),
            losses=len(losses),
        )

        ok, reason = check_ftmo_compliance(result, initial_balance)
        result.ftmo_compliant = ok
        result.ftmo_fail_reason = reason
        result.challenge = simulate_two_step_challenge(result, initial_balance)

        return result
