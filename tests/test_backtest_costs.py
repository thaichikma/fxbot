"""Unit tests for backtest transaction cost model."""

from datetime import datetime, timezone

from backtest.costs import (
    rollover_nights_utc,
    spread_pips_from_mode,
    trade_transaction_costs_usd,
)


def test_spread_pips_eurusd_typical_one_pip():
    spec = {"pip_size": 0.0001, "point_size": 0.00001, "typical_spread_points": 10}
    assert abs(spread_pips_from_mode(spec, {}, "typical") - 1.0) < 1e-9


def test_spread_pips_none():
    spec = {"pip_size": 0.0001, "point_size": 0.00001, "typical_spread_points": 10}
    assert spread_pips_from_mode(spec, {}, "none") == 0.0


def test_rollover_nights_next_day():
    a = datetime(2025, 1, 1, 22, 0, tzinfo=timezone.utc)
    b = datetime(2025, 1, 2, 1, 0, tzinfo=timezone.utc)
    assert rollover_nights_utc(a, b) == 1


def test_rollover_same_day():
    a = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
    b = datetime(2025, 1, 1, 18, 0, tzinfo=timezone.utc)
    assert rollover_nights_utc(a, b) == 0


def test_trade_costs_positive_with_spread():
    settings = {
        "pairs": [{"symbol": "EURUSD", "min_volume": 0.01, "volume_step": 0.01, "max_spread_points": 20}],
        "risk": {"risk_per_trade": 0.01, "max_lot_size": 1.0},
        "backtest": {"costs": {"enabled": True, "spread_mode": "typical", "commission_usd_per_lot_round_turn": 0.0}},
    }
    spec = {
        "pip_size": 0.0001,
        "point_size": 0.00001,
        "typical_spread_points": 10,
        "pip_value_per_lot": 10.0,
    }
    costs_cfg = settings["backtest"]["costs"]
    total, br = trade_transaction_costs_usd(
        settings=settings,
        symbol="EURUSD",
        direction="BUY",
        entry_time=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
        exit_time=datetime(2025, 1, 1, 14, 0, tzinfo=timezone.utc),
        equity_at_entry=10_000.0,
        entry_price=1.1,
        sl_price=1.09,
        spec=spec,
        costs_cfg=costs_cfg,
    )
    assert total > 0
    assert br["spread"] > 0
    assert br["commission"] == 0.0
