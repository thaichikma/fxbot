"""H1/M5 engine smoke tests."""

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from src.strategy.h1_m5_engine import H1M5Engine


@pytest.fixture
def specs():
    return {"EURUSD": {"pip_size": 0.0001}}


@pytest.fixture
def strat():
    return {
        "fvg_min_size_pips": 1,
        "sl_buffer_pips": 5,
        "tp_ratios": [1.5, 2.0, 3.0],
        "signal_expiry_minutes": 60,
        "max_signals_per_scan_per_symbol": 2,
    }


def _synth_h1_m5():
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    p = 1.1000
    for i in range(200):
        t = t0 + timedelta(minutes=5 * i)
        rows.append(
            {
                "time": t,
                "open": p,
                "high": p + 0.0005,
                "low": p - 0.0005,
                "close": p + 0.0001,
            }
        )
    m5 = pd.DataFrame(rows)
    h1 = m5.set_index("time").resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna().reset_index()
    return h1, m5


def test_h1_m5_engine_runs(strat, specs):
    h1, m5 = _synth_h1_m5()
    eng = H1M5Engine(strat, specs)
    out = eng.analyze("EURUSD", {"H1": h1, "M5": m5})
    assert isinstance(out, list)
