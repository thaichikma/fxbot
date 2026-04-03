"""
Daily Tracker — Track daily PnL, trading days, best day, request counter.

Responsibilities:
- Track realized & unrealized PnL per day
- Track best day profit for FTMO Best Day Rule
- Count trading days (days with at least 1 trade)
- Count MT5 API requests per day (hyperactivity limit)
- Reset at midnight CE(S)T (FTMO's daily boundary)
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from loguru import logger

from src.utils.timezone import cest_now

if TYPE_CHECKING:
    from src.data.db import Database


class DailyTracker:
    """
    Tracks daily metrics for FTMO rule compliance.

    Updates in real-time and persists to database at intervals.
    Daily reset happens at midnight CE(S)T.
    """

    def __init__(self, starting_balance: float = 10000.0):
        self._today_date: str = ""
        self._starting_balance: float = starting_balance
        self._realized_pnl: float = 0.0
        self._unrealized_pnl: float = 0.0
        self._max_equity: float = starting_balance
        self._min_equity: float = starting_balance
        self._trade_count: int = 0
        self._opens_today: int = 0
        self._winning_trades: int = 0
        self._losing_trades: int = 0
        self._request_count: int = 0

        # Historical data (loaded from DB)
        self._all_daily_pnl: list[dict] = []

        # Initialize today
        self._check_and_reset()

    def _check_and_reset(self) -> bool:
        """Check if day changed (CE(S)T) and reset if needed."""
        today = cest_now().strftime("%Y-%m-%d")
        if today != self._today_date:
            if self._today_date:
                logger.info(
                    "Daily reset | date={} → {} | PnL={:.2f}",
                    self._today_date, today, self._realized_pnl,
                )
                # Save yesterday's data to history
                self._all_daily_pnl.append(self._get_today_snapshot())
            self._today_date = today
            self._realized_pnl = 0.0
            self._unrealized_pnl = 0.0
            self._trade_count = 0
            self._opens_today = 0
            self._winning_trades = 0
            self._losing_trades = 0
            self._request_count = 0
            return True
        return False

    def _get_today_snapshot(self) -> dict:
        """Get current day's data as dict."""
        return {
            "date": self._today_date,
            "starting_balance": self._starting_balance,
            "ending_balance": self._starting_balance + self._realized_pnl,
            "realized_pnl": self._realized_pnl,
            "unrealized_pnl": self._unrealized_pnl,
            "max_equity": self._max_equity,
            "min_equity": self._min_equity,
            "trade_count": self._trade_count,
            "winning_trades": self._winning_trades,
            "losing_trades": self._losing_trades,
            "request_count": self._request_count,
        }

    # ─── Update Methods ──────────────────────────────────────

    def check_reset(self) -> bool:
        """Called from main loop — checks and performs daily reset."""
        return self._check_and_reset()

    def update_balance(self, new_balance: float) -> None:
        """Update starting balance (called at daily reset)."""
        self._starting_balance = new_balance

    def record_trade_opened(self) -> None:
        """Count a new position open (for max daily trades / FTMO guardian)."""
        self._check_and_reset()
        self._opens_today += 1

    def record_trade_closed(self, pnl: float) -> None:
        """Record a closed trade's PnL."""
        self._check_and_reset()
        self._realized_pnl += pnl
        self._trade_count += 1
        if pnl > 0:
            self._winning_trades += 1
        elif pnl < 0:
            self._losing_trades += 1
        logger.debug("Trade recorded: PnL={:.2f} | Daily total={:.2f}", pnl, self._realized_pnl)

    def update_unrealized(self, unrealized_pnl: float) -> None:
        """Update current unrealized PnL from open positions."""
        self._unrealized_pnl = unrealized_pnl

    def update_equity(self, equity: float) -> None:
        """Update equity high/low watermarks."""
        self._max_equity = max(self._max_equity, equity)
        self._min_equity = min(self._min_equity, equity)

    def increment_request(self) -> None:
        """Increment daily MT5 request counter."""
        self._request_count += 1

    def sync_requests(self, count: int) -> None:
        """Mirror MT5 client request counter (hyperactivity tracking)."""
        self._check_and_reset()
        self._request_count = max(self._request_count, int(count))

    def load_history(self, daily_records: list[dict]) -> None:
        """Load historical daily PnL from database."""
        self._all_daily_pnl = daily_records
        logger.info("Loaded {} days of PnL history", len(daily_records))

    # ─── Query Methods ────────────────────────────────────────

    @property
    def today_date(self) -> str:
        self._check_and_reset()
        return self._today_date

    def get_daily_pnl(self) -> float:
        """Current day's realized + unrealized PnL."""
        self._check_and_reset()
        return self._realized_pnl + self._unrealized_pnl

    def get_today_realized_pnl(self) -> float:
        """Current day's realized PnL only."""
        self._check_and_reset()
        return self._realized_pnl

    def get_today_profit(self) -> float:
        """Today's positive PnL (for best day rule). Returns 0 if negative."""
        pnl = self.get_today_realized_pnl()
        return max(0.0, pnl)

    def get_total_positive_days_profit(self) -> float:
        """Sum of all positive days' realized PnL (for best day rule)."""
        total = sum(
            d["realized_pnl"]
            for d in self._all_daily_pnl
            if d.get("realized_pnl", 0) > 0
        )
        # Add today if positive
        if self._realized_pnl > 0:
            total += self._realized_pnl
        return total

    def get_best_day_profit(self) -> float:
        """Highest single day profit across all history + today."""
        profits = [
            d["realized_pnl"]
            for d in self._all_daily_pnl
            if d.get("realized_pnl", 0) > 0
        ]
        if self._realized_pnl > 0:
            profits.append(self._realized_pnl)
        return max(profits) if profits else 0.0

    def get_best_day_ratio(self) -> float:
        """Best day profit as percentage of total positive days profit."""
        total = self.get_total_positive_days_profit()
        if total <= 0:
            return 0.0
        best = self.get_best_day_profit()
        return best / total

    def get_trading_days_count(self) -> int:
        """Number of unique days with at least 1 trade."""
        count = sum(1 for d in self._all_daily_pnl if d.get("trade_count", 0) > 0)
        if self._trade_count > 0:
            count += 1
        return count

    def get_today_trade_count(self) -> int:
        """Number of closed trades today (legacy name)."""
        self._check_and_reset()
        return self._trade_count

    def get_today_open_count(self) -> int:
        """Positions opened today (for max daily trades guard)."""
        self._check_and_reset()
        return self._opens_today

    def get_today_request_count(self) -> int:
        """Number of MT5 API requests today."""
        self._check_and_reset()
        return self._request_count

    def get_overall_pnl(self) -> float:
        """Total PnL since challenge start."""
        historical = sum(d.get("realized_pnl", 0) for d in self._all_daily_pnl)
        return historical + self._realized_pnl

    def get_snapshot(self) -> dict:
        """Get full snapshot for Telegram /ftmo command."""
        self._check_and_reset()
        return {
            "date": self._today_date,
            "daily_pnl": self.get_daily_pnl(),
            "daily_realized": self._realized_pnl,
            "daily_unrealized": self._unrealized_pnl,
            "trade_count": self._trade_count,
            "wins": self._winning_trades,
            "losses": self._losing_trades,
            "request_count": self._request_count,
            "overall_pnl": self.get_overall_pnl(),
            "trading_days": self.get_trading_days_count(),
            "best_day_profit": self.get_best_day_profit(),
            "best_day_ratio": self.get_best_day_ratio(),
            "total_positive_profit": self.get_total_positive_days_profit(),
        }
