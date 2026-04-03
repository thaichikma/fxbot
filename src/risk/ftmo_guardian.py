"""
FTMO Guardian — Safety valve for FTMO rule enforcement.

This is the MOST CRITICAL module in the system.
Every order MUST pass through FTMOGuardian.can_open_trade() before execution.
It enforces:
1. Daily loss limit (5% with 20% buffer → trigger at 4%)
2. Overall drawdown limit (10% with 10% buffer → trigger at 9%)
3. Best day profit cap (50% rule with buffer → cap at 40%)
4. Hyperactivity limit (2000 requests with buffer → stop at 1800)
5. Max concurrent positions
6. Max daily trades
7. Spread validation

This module must have 100% test coverage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from src.data.models import Signal
    from src.risk.daily_tracker import DailyTracker


@dataclass
class GuardianConfig:
    """FTMO Guardian configuration (loaded from ftmo_rules.yaml)."""
    # Limits
    max_daily_loss_pct: float = 0.05
    max_overall_loss_pct: float = 0.10
    max_single_day_profit_pct: float = 0.50

    # Buffers
    daily_loss_trigger_pct: float = 0.80    # Trigger at 80% of limit
    overall_loss_trigger_pct: float = 0.90  # Trigger at 90% of limit
    best_day_cap_pct: float = 0.40          # Cap at 40%
    hyperactivity_buffer: int = 200

    # Hard limits
    max_requests_per_day: int = 2000
    max_open_orders: int = 200

    # User limits (from settings.yaml)
    max_concurrent_trades: int = 3
    max_daily_trades: int = 8


@dataclass
class GuardianCheck:
    """Result of a guardian check."""
    approved: bool
    reason: str
    check_name: str = ""
    severity: str = "info"  # info, warning, critical


class FTMOGuardian:
    """
    FTMO Rule Enforcer — The safety valve.

    Usage:
        guardian = FTMOGuardian(config, tracker, initial_balance=10000)
        approved, reason = guardian.can_open_trade(signal, lot_size, current_equity, spread)
        if not approved:
            # DO NOT execute the trade
            log_and_notify(reason)
    """

    def __init__(
        self,
        config: GuardianConfig,
        tracker: DailyTracker,
        initial_balance: float = 10000.0,
    ):
        self.config = config
        self.tracker = tracker
        self.initial_balance = initial_balance
        self._kill_switch_active = False
        self._daily_limit_breached = False

        # Pre-calculate dollar limits
        self._max_daily_loss = initial_balance * config.max_daily_loss_pct
        self._daily_loss_buffer = self._max_daily_loss * config.daily_loss_trigger_pct
        self._max_overall_loss = initial_balance * config.max_overall_loss_pct
        self._min_equity = initial_balance * (1 - config.max_overall_loss_pct)
        self._overall_buffer_equity = self._min_equity + (
            initial_balance * (1 - config.overall_loss_trigger_pct) * config.max_overall_loss_pct
        )

        logger.info(
            "FTMO Guardian initialized | balance={} | daily_limit={} | buffer={} | min_equity={}",
            initial_balance, self._max_daily_loss, self._daily_loss_buffer, self._min_equity,
        )

    @property
    def kill_switch_active(self) -> bool:
        return self._kill_switch_active

    # ─── Main Entry Point ─────────────────────────────────────

    def can_open_trade(
        self,
        signal: Signal,
        lot_size: float,
        current_equity: float,
        current_spread: int = 0,
        max_spread: int = 0,
    ) -> tuple[bool, str]:
        """
        Pre-trade validation — checks ALL FTMO rules.

        Args:
            signal: The trading signal
            lot_size: Calculated lot size
            current_equity: Current account equity
            current_spread: Current spread in points
            max_spread: Max allowed spread in points

        Returns:
            (approved: bool, reason: str)
        """
        if self._kill_switch_active:
            return False, "🚫 KILL SWITCH ACTIVE — all trading halted"

        checks = [
            self._check_daily_loss(),
            self._check_overall_drawdown(current_equity),
            self._check_best_day_profit(),
            self._check_hyperactivity(),
            self._check_max_positions(),
            self._check_max_daily_trades(),
            self._check_spread(current_spread, max_spread),
        ]

        for check in checks:
            if not check.approved:
                logger.warning(
                    "Trade BLOCKED | check={} | reason={} | severity={}",
                    check.check_name, check.reason, check.severity,
                )
                return False, check.reason

        logger.info("Trade APPROVED by FTMO Guardian")
        return True, "APPROVED"

    # ─── Individual Checks ────────────────────────────────────

    def _check_daily_loss(self) -> GuardianCheck:
        """Check if daily PnL is approaching the daily loss limit."""
        daily_pnl = self.tracker.get_daily_pnl()

        if daily_pnl <= -self._max_daily_loss:
            self._daily_limit_breached = True
            return GuardianCheck(
                approved=False,
                reason=f"🔴 DAILY LIMIT BREACHED: PnL ${daily_pnl:.2f} ≤ -${self._max_daily_loss:.2f}",
                check_name="daily_loss",
                severity="critical",
            )

        if daily_pnl <= -self._daily_loss_buffer:
            return GuardianCheck(
                approved=False,
                reason=f"⚠️ Daily loss approaching limit: ${daily_pnl:.2f} / -${self._max_daily_loss:.2f} (buffer at -${self._daily_loss_buffer:.2f})",
                check_name="daily_loss",
                severity="warning",
            )

        return GuardianCheck(approved=True, reason="", check_name="daily_loss")

    def _check_overall_drawdown(self, equity: float) -> GuardianCheck:
        """Check if equity is approaching the max drawdown limit."""
        if equity <= self._min_equity:
            self._kill_switch_active = True
            return GuardianCheck(
                approved=False,
                reason=f"🔴 MAX DRAWDOWN BREACHED: Equity ${equity:.2f} ≤ ${self._min_equity:.2f}. KILL SWITCH ACTIVATED.",
                check_name="overall_drawdown",
                severity="critical",
            )

        if equity <= self._overall_buffer_equity:
            return GuardianCheck(
                approved=False,
                reason=f"⚠️ Equity approaching limit: ${equity:.2f} / ${self._min_equity:.2f} (buffer at ${self._overall_buffer_equity:.2f})",
                check_name="overall_drawdown",
                severity="warning",
            )

        return GuardianCheck(approved=True, reason="", check_name="overall_drawdown")

    def _check_best_day_profit(self) -> GuardianCheck:
        """Check if today's profit would violate the Best Day Rule."""
        today_profit = self.tracker.get_today_profit()
        total_positive = self.tracker.get_total_positive_days_profit()

        if total_positive <= 0:
            # No history yet — allow trading
            return GuardianCheck(approved=True, reason="", check_name="best_day")

        # Calculate what percentage today's profit is of total
        best_day_ratio = today_profit / total_positive if total_positive > 0 else 0

        if best_day_ratio >= self.config.best_day_cap_pct:
            return GuardianCheck(
                approved=False,
                reason=f"⚠️ Best Day Rule: Today ${today_profit:.2f} = {best_day_ratio:.0%} of total ${total_positive:.2f} (cap at {self.config.best_day_cap_pct:.0%})",
                check_name="best_day",
                severity="warning",
            )

        return GuardianCheck(approved=True, reason="", check_name="best_day")

    def _check_hyperactivity(self) -> GuardianCheck:
        """Check if approaching MT5 request limit."""
        requests = self.tracker.get_today_request_count()
        limit = self.config.max_requests_per_day - self.config.hyperactivity_buffer

        if requests >= limit:
            return GuardianCheck(
                approved=False,
                reason=f"⚠️ Hyperactivity: {requests}/{self.config.max_requests_per_day} requests (buffer at {limit})",
                check_name="hyperactivity",
                severity="warning",
            )

        return GuardianCheck(approved=True, reason="", check_name="hyperactivity")

    def _check_max_positions(self) -> GuardianCheck:
        """Check max concurrent positions."""
        # This will be called with actual position count from order_manager
        # For now, return approved — the actual check happens in the main loop
        return GuardianCheck(approved=True, reason="", check_name="max_positions")

    def _check_max_daily_trades(self) -> GuardianCheck:
        """Check max new positions opened per day."""
        open_count = self.tracker.get_today_open_count()
        if open_count >= self.config.max_daily_trades:
            return GuardianCheck(
                approved=False,
                reason=f"⚠️ Max daily trades reached: {open_count}/{self.config.max_daily_trades}",
                check_name="max_daily_trades",
                severity="warning",
            )

        return GuardianCheck(approved=True, reason="", check_name="max_daily_trades")

    def _check_spread(self, current_spread: int, max_spread: int) -> GuardianCheck:
        """Check if current spread is acceptable."""
        if max_spread > 0 and current_spread > max_spread:
            return GuardianCheck(
                approved=False,
                reason=f"⚠️ Spread too high: {current_spread} > {max_spread} points",
                check_name="spread",
                severity="info",
            )

        return GuardianCheck(approved=True, reason="", check_name="spread")

    # ─── External Checks (called with live data) ──────────────

    def check_positions_limit(self, current_open: int) -> tuple[bool, str]:
        """Check if we can open another position (called separately)."""
        if current_open >= self.config.max_concurrent_trades:
            return False, f"Max positions reached: {current_open}/{self.config.max_concurrent_trades}"
        return True, ""

    # ─── Equity Monitor ───────────────────────────────────────

    def monitor_equity(self, equity: float) -> tuple[bool, str]:
        """
        Real-time equity monitor — called every scan interval.
        Returns (is_safe, message).
        If not safe, caller should trigger emergency_close_all.
        """
        # Hard limit — no buffer
        if equity <= self._min_equity:
            self._kill_switch_active = True
            return False, f"🚨 EMERGENCY: Equity ${equity:.2f} ≤ min ${self._min_equity:.2f}"

        # Check daily PnL
        daily_pnl = self.tracker.get_daily_pnl()
        if daily_pnl <= -self._max_daily_loss:
            self._daily_limit_breached = True
            return False, f"🚨 EMERGENCY: Daily loss ${daily_pnl:.2f} ≤ -${self._max_daily_loss:.2f}"

        return True, ""

    # ─── Kill Switch ──────────────────────────────────────────

    def activate_kill_switch(self, reason: str = "Manual") -> None:
        """Activate kill switch — stops all trading."""
        self._kill_switch_active = True
        logger.critical("🚨 KILL SWITCH ACTIVATED: {}", reason)

    def deactivate_kill_switch(self) -> None:
        """Deactivate kill switch — requires manual intervention."""
        self._kill_switch_active = False
        self._daily_limit_breached = False
        logger.warning("Kill switch deactivated — trading resumed")

    # ─── Status ───────────────────────────────────────────────

    def get_status(self, current_equity: float) -> dict:
        """Get full FTMO status for Telegram display."""
        daily_pnl = self.tracker.get_daily_pnl()
        daily_pct = (daily_pnl / self.initial_balance) * 100 if self.initial_balance else 0
        overall_pnl = self.tracker.get_overall_pnl()
        overall_pct = (overall_pnl / self.initial_balance) * 100 if self.initial_balance else 0
        dd_pct = ((self.initial_balance - current_equity) / self.initial_balance) * 100

        return {
            "kill_switch": self._kill_switch_active,
            "daily_limit_breached": self._daily_limit_breached,
            "daily_pnl": daily_pnl,
            "daily_pnl_pct": daily_pct,
            "daily_limit": self._max_daily_loss,
            "daily_buffer": self._daily_loss_buffer,
            "daily_usage_pct": abs(daily_pnl / self._max_daily_loss * 100) if self._max_daily_loss else 0,
            "equity": current_equity,
            "min_equity": self._min_equity,
            "drawdown_pct": dd_pct,
            "overall_pnl": overall_pnl,
            "overall_pnl_pct": overall_pct,
            "best_day_ratio": self.tracker.get_best_day_ratio() * 100,
            "trading_days": self.tracker.get_trading_days_count(),
            "today_trades": self.tracker.get_today_open_count(),
            "today_requests": self.tracker.get_today_request_count(),
        }
