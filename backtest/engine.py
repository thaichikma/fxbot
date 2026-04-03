"""
Backtest engine — walk-forward SMC signals + simplified fill model + FTMO metrics.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
from loguru import logger

from backtest.costs import costs_feature_enabled, trade_transaction_costs_usd
from backtest.data_loader import build_multi_timeframe
from backtest.ftmo_challenge import check_ftmo_compliance, simulate_two_step_challenge
from backtest.result import BacktestResult, SimulatedTrade
from src.strategy.smc_engine import SMCEngine


def _ensure_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _m15_bar_index_for_ts(m15: pd.DataFrame, exit_t: datetime) -> int:
    """Chỉ số nến M15 chứa thời điểm exit (time = mở nến, chuỗi tăng dần)."""
    ts = pd.Timestamp(exit_t)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    ot = pd.to_datetime(m15["time"], utc=True)
    pos = int(ot.searchsorted(ts, side="right")) - 1
    return max(0, min(pos, len(m15) - 1))


def _simulate_exit_m1(
    m1: pd.DataFrame,
    entry_time: datetime,
    direction: str,
    entry: float,
    sl: float,
    tp: float,
    max_m1_bars: int = 1440,
) -> tuple[str, datetime, float]:
    """
    Đánh giá SL/TP trên chuỗi M1 (độ phân giải cao).
    Bắt đầu từ nến M1 đầu tiên có time > entry_time (sau khi đóng nến M15 tín hiệu).
    Quy tắc cùng nến: SL trước (conservative).
    """
    m1 = m1.sort_values("time").reset_index(drop=True)
    et = pd.Timestamp(entry_time)
    if et.tzinfo is None:
        et = et.tz_localize("UTC")
    starts = pd.to_datetime(m1["time"], utc=True)
    j0 = int(starts.searchsorted(et, side="right"))
    end = min(j0 + max_m1_bars, len(m1))
    if j0 >= len(m1):
        return "timeout", _ensure_utc(et.to_pydatetime()), float(entry)

    for j in range(j0, end):
        row = m1.iloc[j]
        lo = float(row["low"])
        hi = float(row["high"])
        ex_t = _ensure_utc(pd.Timestamp(row["time"]).to_pydatetime())
        if direction == "BUY":
            if lo <= sl:
                return "loss", ex_t, sl
            if hi >= tp:
                return "win", ex_t, tp
        else:
            if hi >= sl:
                return "loss", ex_t, sl
            if lo <= tp:
                return "win", ex_t, tp
    last = m1.iloc[end - 1]
    last_t = _ensure_utc(pd.Timestamp(last["time"]).to_pydatetime())
    return "timeout", last_t, float(last["close"])


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
        self._symbols_specs = symbols_specs
        strategy = dict(settings.get("strategy", {}))
        self._risk_pct = float(settings.get("risk", {}).get("risk_per_trade", 0.01))
        self._smc = SMCEngine(strategy, symbols_specs)
        self._costs_cfg = dict(settings.get("backtest", {}).get("costs", {}))
        self._costs_enabled = costs_feature_enabled(settings)

    def run(
        self,
        symbol: str,
        m15: pd.DataFrame,
        *,
        initial_balance: float = 10_000.0,
        step_bars: int = 4,
        min_m15_bars: int = 120,
        cooldown_bars: int = 8,
        m1: pd.DataFrame | None = None,
        max_m15_bars_for_exit: int = 96,
    ) -> BacktestResult:
        """
        Walk forward on M15; resample H1/H4 internally.

        Args:
            symbol: e.g. EURUSD
            m15: DataFrame with time, open, high, low, close (UTC)
            initial_balance: starting equity
            step_bars: only run SMC every N M15 bars (perf)
            min_m15_bars: minimum history before first signal
            m1: nếu có — đánh giá đường đi SL/TP trên M1 (entry vẫn từ SMC trên M15)
            max_m15_bars_for_exit: giới hạn thời gian chờ lệnh (quy đổi ≈ ×15 nến M1)
        """
        m15 = m15.sort_values("time").reset_index(drop=True)
        if len(m15) < min_m15_bars:
            raise ValueError(f"Need at least {min_m15_bars} M15 bars")

        use_m1_exit = m1 is not None and len(m1) > 0
        if use_m1_exit:
            m1 = m1.sort_values("time").reset_index(drop=True)
            t0, t1 = m15["time"].min(), m15["time"].max()
            m1 = m1[(m1["time"] >= t0) & (m1["time"] <= t1)].reset_index(drop=True)
            if len(m1) < 10:
                logger.warning("M1 sau khi cắt theo M15 quá ngắn — tắt exit M1, dùng M15")
                use_m1_exit = False
        max_m1_bars = max(1, max_m15_bars_for_exit * 15)

        frames = build_multi_timeframe(m15)
        m15 = frames["M15"]
        h1 = frames["H1"]
        h4 = frames["H4"]

        equity = initial_balance
        equity_curve: list[tuple[datetime, float]] = [(m15.iloc[min_m15_bars]["time"], equity)]
        trades: list[SimulatedTrade] = []
        daily_pnls: dict[str, float] = {}
        total_costs_usd = 0.0
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

            if use_m1_exit:
                outcome, exit_t_dt, exit_px = _simulate_exit_m1(
                    m1, t, direction, entry, sl, tp, max_m1_bars=max_m1_bars
                )
                exit_j = _m15_bar_index_for_ts(m15, exit_t_dt)
            else:
                outcome, exit_j, exit_px = _simulate_exit(
                    m15, i + 1, direction, entry, sl, tp, max_bars=max_m15_bars_for_exit
                )
                exit_t_dt = _ensure_utc(pd.Timestamp(m15.iloc[exit_j]["time"]).to_pydatetime())

            risk = equity * self._risk_pct
            sl_dist = abs(entry - sl)
            if sl_dist < 1e-12:
                continue
            rr = abs(tp - entry) / sl_dist

            if outcome == "win":
                pnl_gross = risk * rr
            elif outcome == "loss":
                pnl_gross = -risk
            else:
                move = (exit_px - entry) if direction == "BUY" else (entry - exit_px)
                pnl_gross = risk * (move / sl_dist) if sl_dist else 0.0

            exit_t = exit_t_dt

            cost_usd = 0.0
            spec = self._symbols_specs.get(symbol.upper(), {})
            if self._costs_enabled and spec:
                cost_usd, _br = trade_transaction_costs_usd(
                    settings=self._settings,
                    symbol=symbol,
                    direction=direction,
                    entry_time=t,
                    exit_time=exit_t,
                    equity_at_entry=equity,
                    entry_price=entry,
                    sl_price=sl,
                    spec=spec,
                    costs_cfg=self._costs_cfg,
                )
                total_costs_usd += cost_usd

            pnl = pnl_gross - cost_usd
            equity += pnl
            min_equity = min(min_equity, equity)

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
                    pnl_gross=pnl_gross,
                    transaction_costs_usd=cost_usd,
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
            total_transaction_costs_usd=total_costs_usd,
            costs_enabled=self._costs_enabled,
            m1_resolution_for_exit=bool(use_m1_exit),
        )

        ok, reason = check_ftmo_compliance(result, initial_balance)
        result.ftmo_compliant = ok
        result.ftmo_fail_reason = reason
        result.challenge = simulate_two_step_challenge(result, initial_balance)

        return result
