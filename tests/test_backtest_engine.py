"""Backtest engine smoke tests."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from backtest.engine import BacktestEngine
from backtest.run import run_backtest_report


@pytest.fixture
def settings():
    return {
        "risk": {"risk_per_trade": 0.01},
        "strategy": {
            "fvg_min_size_pips": 1,
            "sl_buffer_pips": 5,
            "tp_ratios": [1.5, 2.0, 3.0],
            "signal_expiry_minutes": 60,
            "max_signals_per_scan_per_symbol": 2,
        },
    }


@pytest.fixture
def specs():
    return {"EURUSD": {"pip_size": 0.0001, "pip_value_per_lot": 10.0}}


def _synth_m15(n: int = 400) -> pd.DataFrame:
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    p = 1.1000
    for i in range(n):
        t = t0 + timedelta(minutes=15 * i)
        p += 0.00002
        rows.append(
            {
                "time": t,
                "open": p,
                "high": p + 0.0003,
                "low": p - 0.0002,
                "close": p + 0.0001,
            }
        )
    return pd.DataFrame(rows)


def test_engine_run_smoke(settings, specs):
    eng = BacktestEngine(settings, specs)
    m15 = _synth_m15(400)
    r = eng.run("EURUSD", m15, initial_balance=10_000.0, step_bars=8, min_m15_bars=100)
    assert r.initial_balance == 10_000.0
    assert r.final_balance >= 0
    assert r.total_trades >= 0
    assert isinstance(r.ftmo_compliant, bool)
    assert "final_phase" in r.challenge


def test_run_backtest_report_uses_project_config(tmp_path):
    """run_backtest_report loads config từ project root + CSV tuyệt đối."""
    root = Path(__file__).resolve().parent.parent
    csv_path = tmp_path / "m15.csv"
    _synth_m15(200).to_csv(csv_path, index=False)
    text = run_backtest_report(
        root,
        symbol="EURUSD",
        csv=csv_path,
        min_m15_bars=100,
        include_paper_summary=False,
    )
    assert "EURUSD" in text
    assert "Paper validation" not in text
