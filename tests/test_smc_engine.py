"""Tests for SMCEngine."""

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from src.data.models import Direction
from src.strategy.smc_engine import SMCEngine


def _trending_h4_bull(n: int = 120) -> pd.DataFrame:
    t0 = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    rows = []
    p = 1.1000
    for i in range(n):
        p += 0.0002
        rows.append(
            {
                "time": t0 + timedelta(hours=i),
                "open": p,
                "high": p + 0.0003,
                "low": p - 0.0001,
                "close": p + 0.0001,
            }
        )
    return pd.DataFrame(rows)


def _h1_bull(n: int = 200) -> pd.DataFrame:
    return _trending_h4_bull(n)


def _m15_with_bullish_fvg() -> pd.DataFrame:
    """Last bar: bullish FVG — low[i] > high[i-2]."""
    t0 = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    rows = []
    base = 1.1000
    for i in range(50):
        o = base + i * 0.0001
        rows.append(
            {
                "time": t0 + timedelta(minutes=15 * i),
                "open": o,
                "high": o + 0.0002,
                "low": o - 0.0001,
                "close": o + 0.0001,
            }
        )
    # i=49: set i-2 high low, i low high for gap
    i = 49
    rows[i - 2]["high"] = 1.1050
    rows[i - 2]["low"] = 1.1040
    rows[i - 1]["close"] = 1.1060
    rows[i]["low"] = 1.1065  # > 1.1050
    rows[i]["high"] = 1.1070
    return pd.DataFrame(rows)


@pytest.fixture
def specs():
    return {
        "EURUSD": {
            "pip_size": 0.0001,
            "pip_value_per_lot": 10.0,
        }
    }


@pytest.fixture
def strategy_cfg():
    return {
        "swing_length": 10,
        "fvg_min_size_pips": 1,
        "sl_buffer_pips": 5,
        "tp_ratios": [1.5, 2.0, 3.0],
        "signal_expiry_minutes": 60,
        "max_signals_per_scan_per_symbol": 2,
    }


def test_analyze_returns_signal_when_fvg_present(specs, strategy_cfg):
    eng = SMCEngine(strategy_cfg, specs)
    data = {
        "H4": _trending_h4_bull(),
        "H1": _h1_bull(),
        "M15": _m15_with_bullish_fvg(),
    }
    out = eng.analyze("EURUSD", data)
    assert isinstance(out, list)
    assert len(out) >= 1
    s = out[0]
    assert s.symbol == "EURUSD"
    assert s.direction == Direction.BUY
    assert s.sl_distance_pips > 0


def test_analyze_empty_when_no_data(specs, strategy_cfg):
    eng = SMCEngine(strategy_cfg, specs)
    assert eng.analyze("EURUSD", {"H4": pd.DataFrame(), "H1": pd.DataFrame(), "M15": pd.DataFrame()}) == []
