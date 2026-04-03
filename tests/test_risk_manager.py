"""Tests for RiskManager."""

import pytest

from src.data.models import Direction, MarketBias, Signal, SignalStatus, SignalType, StructureType
from src.risk.risk_manager import RiskManager


@pytest.fixture
def settings():
    return {
        "pairs": [{"symbol": "EURUSD", "min_volume": 0.01, "volume_step": 0.01}],
        "risk": {
            "risk_per_trade": 0.01,
            "max_lot_size": 1.0,
            "max_correlation_trades": 2,
        },
        "correlation_groups": {
            "usd_pairs": ["EURUSD", "GBPUSD"],
        },
    }


@pytest.fixture
def specs():
    return {"EURUSD": {"pip_value_per_lot": 10.0, "pip_size": 0.0001}}


def test_calculate_lot_size(settings, specs):
    rm = RiskManager(settings, specs, None)
    lot = rm.calculate_lot_size("EURUSD", 30.0, 10000.0)
    assert lot >= 0.01


def test_correlation_blocks_third_same_direction(settings, specs):
    rm = RiskManager(settings, specs, None)
    sig = Signal(
        symbol="EURUSD",
        direction=Direction.BUY,
        signal_type=SignalType.FVG_FILL,
        entry_price=1.1,
        stop_loss=1.09,
        take_profit_1=1.12,
        take_profit_2=1.13,
        take_profit_3=1.14,
        h4_bias=MarketBias.BULLISH,
        h1_structure=StructureType.BOS,
        status=SignalStatus.PENDING,
    )
    pos = [
        {"symbol": "EURUSD", "type": "BUY"},
        {"symbol": "GBPUSD", "type": "BUY"},
    ]
    ok, reason = rm.check_correlation(sig, pos)
    assert ok is False
    assert "Correlation" in reason
