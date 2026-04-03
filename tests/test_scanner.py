"""Tests for SignalScanner."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.strategy.news_filter import NewsFilter
from src.strategy.scanner import SignalScanner
from src.strategy.session_filter import SessionFilter
from src.strategy.smc_engine import SMCEngine


@pytest.fixture
def sessions_cfg():
    return {
        "london": {"start": "07:00", "end": "16:00", "auto_trade": True},
        "new_york": {"start": "12:30", "end": "21:00", "auto_trade": True},
        "asian": {"start": "23:00", "end": "07:00", "auto_trade": False},
    }


@pytest.fixture
def settings_min(sessions_cfg):
    return {
        "sessions": sessions_cfg,
        "pairs": [{"symbol": "EURUSD", "enabled": True, "timeframes": {"bias": "H4", "structure": "H1", "entry": "M15"}}],
        "strategy": {
            "fvg_min_size_pips": 1,
            "sl_buffer_pips": 5,
            "tp_ratios": [1.5, 2.0, 3.0],
            "signal_expiry_minutes": 60,
        },
        "system": {
            "signal_scan_enabled": True,
            "signal_dedupe_minutes": 30,
            "max_signals_per_scan_per_symbol": 2,
        },
        "news": {},
    }


@pytest.fixture
def symbol_specs():
    return {"EURUSD": {"pip_size": 0.0001}}


def _df(n=100):
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC"),
            "open": [1.1 + i * 0.0001 for i in range(n)],
            "high": [1.1 + i * 0.0001 + 0.0002 for i in range(n)],
            "low": [1.1 + i * 0.0001 - 0.0001 for i in range(n)],
            "close": [1.1 + i * 0.0001 + 0.00005 for i in range(n)],
        }
    )


@pytest.mark.asyncio
async def test_scan_runs_with_mock_mt5(settings_min, sessions_cfg, symbol_specs):
    mt5 = MagicMock()
    mt5.get_rates = MagicMock(return_value=_df(120))

    strat = dict(settings_min["strategy"])
    strat["max_signals_per_scan_per_symbol"] = 2
    eng = SMCEngine(strat, symbol_specs)
    nf = NewsFilter({})
    nf._cached_events = []
    sc = SignalScanner(
        settings_min,
        symbol_specs,
        SessionFilter(sessions_cfg),
        nf,
        eng,
    )
    now = datetime(2026, 4, 3, 14, 0, tzinfo=timezone.utc)
    out = await sc.scan(mt5, db=None, now=now)
    assert isinstance(out, list)
    mt5.get_rates.assert_called()
