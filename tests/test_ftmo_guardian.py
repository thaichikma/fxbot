"""
Tests for FTMO Guardian — 100% coverage required.

Tests every check:
1. Daily loss limit (normal, buffer, breached)
2. Overall drawdown (normal, buffer, breached → kill switch)
3. Best day profit cap (no history, within cap, exceeds cap)
4. Hyperactivity (normal, limit reached)
5. Max daily trades
6. Spread validation
7. Kill switch activation/deactivation
8. Equity monitoring
"""

import pytest
from unittest.mock import MagicMock

from src.risk.ftmo_guardian import FTMOGuardian, GuardianConfig
from src.risk.daily_tracker import DailyTracker
from src.data.models import Signal, Direction, SignalType, MarketBias, StructureType


@pytest.fixture
def config():
    return GuardianConfig(
        max_daily_loss_pct=0.05,
        max_overall_loss_pct=0.10,
        max_single_day_profit_pct=0.50,
        daily_loss_trigger_pct=0.80,
        overall_loss_trigger_pct=0.90,
        best_day_cap_pct=0.40,
        hyperactivity_buffer=200,
        max_requests_per_day=2000,
        max_open_orders=200,
        max_concurrent_trades=3,
        max_daily_trades=8,
    )


@pytest.fixture
def tracker():
    return DailyTracker(starting_balance=10000.0)


@pytest.fixture
def guardian(config, tracker):
    return FTMOGuardian(config=config, tracker=tracker, initial_balance=10000.0)


@pytest.fixture
def sample_signal():
    return Signal(
        id="test-001",
        symbol="XAUUSD",
        direction=Direction.BUY,
        signal_type=SignalType.OB_PULLBACK,
        entry_price=2650.00,
        stop_loss=2645.00,
        take_profit_1=2657.50,
        take_profit_2=2660.00,
        take_profit_3=2665.00,
        sl_distance_pips=50,
        risk_reward_ratio=1.5,
    )


# ─── Daily Loss Tests ────────────────────────────────────────

class TestDailyLoss:
    def test_normal_daily_pnl_approved(self, guardian, sample_signal):
        """Trade should be approved when daily PnL is within limits."""
        approved, reason = guardian.can_open_trade(sample_signal, 0.02, 10000.0)
        assert approved is True

    def test_daily_loss_at_buffer_blocked(self, guardian, tracker, sample_signal):
        """Trade should be blocked when daily PnL reaches buffer (-$400)."""
        # Simulate daily loss reaching buffer (80% of $500 = $400)
        tracker._realized_pnl = -401.0
        approved, reason = guardian.can_open_trade(sample_signal, 0.02, 10000.0)
        assert approved is False
        assert "Daily loss" in reason or "daily" in reason.lower()

    def test_daily_loss_breached(self, guardian, tracker, sample_signal):
        """Trade should be blocked and flag breached when at limit."""
        tracker._realized_pnl = -500.0
        approved, reason = guardian.can_open_trade(sample_signal, 0.02, 10000.0)
        assert approved is False
        assert guardian._daily_limit_breached is True

    def test_small_daily_loss_approved(self, guardian, tracker, sample_signal):
        """Small daily loss should still allow trading."""
        tracker._realized_pnl = -200.0
        approved, reason = guardian.can_open_trade(sample_signal, 0.02, 10000.0)
        assert approved is True


# ─── Overall Drawdown Tests ──────────────────────────────────

class TestOverallDrawdown:
    def test_healthy_equity_approved(self, guardian, sample_signal):
        """Normal equity should pass."""
        approved, reason = guardian.can_open_trade(sample_signal, 0.02, 10000.0)
        assert approved is True

    def test_equity_at_buffer_blocked(self, guardian, sample_signal):
        """Equity at 90% buffer should be blocked."""
        # Min equity = 9000, buffer adds back some → ~9100
        approved, reason = guardian.can_open_trade(sample_signal, 0.02, 9050.0)
        assert approved is False
        assert "Equity" in reason or "equity" in reason.lower()

    def test_equity_breached_activates_kill_switch(self, guardian, sample_signal):
        """Equity below min should activate kill switch."""
        approved, reason = guardian.can_open_trade(sample_signal, 0.02, 8999.0)
        assert approved is False
        assert guardian.kill_switch_active is True
        assert "KILL SWITCH" in reason

    def test_equity_above_buffer_approved(self, guardian, sample_signal):
        """Equity above buffer should pass."""
        approved, reason = guardian.can_open_trade(sample_signal, 0.02, 9500.0)
        assert approved is True


# ─── Best Day Rule Tests ─────────────────────────────────────

class TestBestDayRule:
    def test_no_history_approved(self, guardian, sample_signal):
        """No positive history — should allow trading."""
        approved, reason = guardian.can_open_trade(sample_signal, 0.02, 10000.0)
        assert approved is True

    def test_within_cap_approved(self, guardian, tracker, sample_signal):
        """Today's profit within 40% cap of total — approved."""
        # History: $500 positive total, today $100 = 20% → OK
        tracker._all_daily_pnl = [{"realized_pnl": 500, "trade_count": 5}]
        tracker._realized_pnl = 100  # Today
        approved, reason = guardian.can_open_trade(sample_signal, 0.02, 10600.0)
        assert approved is True

    def test_exceeds_cap_blocked(self, guardian, tracker, sample_signal):
        """Today's profit exceeds 40% cap — blocked."""
        # History: $300 total positive, today $300 = 50% → blocked at 40%
        tracker._all_daily_pnl = [{"realized_pnl": 300, "trade_count": 3}]
        tracker._realized_pnl = 300  # 300/600 = 50% > 40%
        approved, reason = guardian.can_open_trade(sample_signal, 0.02, 10600.0)
        assert approved is False
        assert "Best Day" in reason


# ─── Hyperactivity Tests ─────────────────────────────────────

class TestHyperactivity:
    def test_normal_requests_approved(self, guardian, sample_signal):
        """Low request count should pass."""
        approved, reason = guardian.can_open_trade(sample_signal, 0.02, 10000.0)
        assert approved is True

    def test_at_limit_blocked(self, guardian, tracker, sample_signal):
        """At request limit buffer — blocked."""
        tracker._request_count = 1801
        approved, reason = guardian.can_open_trade(sample_signal, 0.02, 10000.0)
        assert approved is False
        assert "Hyperactivity" in reason or "hyperactivity" in reason.lower()


# ─── Max Daily Trades Tests ──────────────────────────────────

class TestMaxDailyTrades:
    def test_within_limit_approved(self, guardian, sample_signal):
        """Under trade limit — approved."""
        approved, reason = guardian.can_open_trade(sample_signal, 0.02, 10000.0)
        assert approved is True

    def test_at_limit_blocked(self, guardian, tracker, sample_signal):
        """At max daily trades — blocked."""
        tracker._trade_count = 8
        approved, reason = guardian.can_open_trade(sample_signal, 0.02, 10000.0)
        assert approved is False
        assert "daily trades" in reason.lower()


# ─── Spread Tests ────────────────────────────────────────────

class TestSpread:
    def test_normal_spread_approved(self, guardian, sample_signal):
        """Acceptable spread — approved."""
        approved, reason = guardian.can_open_trade(
            sample_signal, 0.02, 10000.0, current_spread=20, max_spread=50
        )
        assert approved is True

    def test_high_spread_blocked(self, guardian, sample_signal):
        """Excessive spread — blocked."""
        approved, reason = guardian.can_open_trade(
            sample_signal, 0.02, 10000.0, current_spread=60, max_spread=50
        )
        assert approved is False
        assert "Spread" in reason


# ─── Kill Switch Tests ───────────────────────────────────────

class TestKillSwitch:
    def test_kill_switch_blocks_all(self, guardian, sample_signal):
        """Active kill switch should block everything."""
        guardian.activate_kill_switch("Test")
        approved, reason = guardian.can_open_trade(sample_signal, 0.02, 10000.0)
        assert approved is False
        assert "KILL SWITCH" in reason

    def test_deactivate_kill_switch(self, guardian, sample_signal):
        """Deactivated kill switch should allow trading."""
        guardian.activate_kill_switch("Test")
        guardian.deactivate_kill_switch()
        approved, reason = guardian.can_open_trade(sample_signal, 0.02, 10000.0)
        assert approved is True


# ─── Equity Monitor Tests ────────────────────────────────────

class TestEquityMonitor:
    def test_safe_equity(self, guardian):
        """Safe equity returns True."""
        safe, msg = guardian.monitor_equity(10000.0)
        assert safe is True

    def test_critical_equity(self, guardian):
        """Critical equity triggers emergency."""
        safe, msg = guardian.monitor_equity(8900.0)
        assert safe is False
        assert guardian.kill_switch_active is True

    def test_daily_loss_emergency(self, guardian, tracker):
        """Daily loss beyond limit triggers emergency."""
        tracker._realized_pnl = -550.0
        safe, msg = guardian.monitor_equity(9500.0)
        assert safe is False


# ─── Position Limit Tests ────────────────────────────────────

class TestPositionLimit:
    def test_within_limit(self, guardian):
        ok, reason = guardian.check_positions_limit(2)
        assert ok is True

    def test_at_limit(self, guardian):
        ok, reason = guardian.check_positions_limit(3)
        assert ok is False


# ─── Status Report Tests ─────────────────────────────────────

class TestStatus:
    def test_get_status(self, guardian):
        status = guardian.get_status(10000.0)
        assert "daily_pnl" in status
        assert "equity" in status
        assert "kill_switch" in status
        assert status["kill_switch"] is False
