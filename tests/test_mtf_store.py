"""SQLite MTF OHLC store + simulation steps."""

from __future__ import annotations

import pandas as pd
import pytest

from backtest.data_loader import build_multi_timeframe
from backtest.simulation_mtf import merge_with_resampled_m15, smc_data_from_store
from src.data.mtf_store import MTFOHLCStore


def test_insert_fetch_count(tmp_path) -> None:
    db = tmp_path / "mtf.db"
    store = MTFOHLCStore(db)
    df = pd.DataFrame(
        {
            "time": pd.date_range("2025-01-01", periods=5, freq="15min", tz="UTC"),
            "open": [1.0] * 5,
            "high": [1.1] * 5,
            "low": [0.9] * 5,
            "close": [1.0] * 5,
        }
    )
    n = store.insert_dataframe(df, "EURUSD", "M15", source="test")
    assert n == 5
    assert store.count_bars("EURUSD", "M15") == 5
    out = store.fetch_range("EURUSD", "M15")
    assert len(out) == 5
    assert list(out.columns) == ["time", "open", "high", "low", "close"]

    tail = store.fetch_last_n("EURUSD", "M15", 3)
    assert len(tail) == 3
    assert tail["time"].is_monotonic_increasing


def test_frames_up_to_and_smc_helper(tmp_path) -> None:
    db = tmp_path / "mtf2.db"
    store = MTFOHLCStore(db)
    t0 = pd.Timestamp("2025-01-01", tz="UTC")
    df = pd.DataFrame(
        {
            "time": [t0 + pd.Timedelta(hours=i) for i in range(10)],
            "open": [2600.0] * 10,
            "high": [2610.0] * 10,
            "low": [2590.0] * 10,
            "close": [2605.0] * 10,
        }
    )
    store.insert_dataframe(df, "XAUUSD", "H1", source="test")
    as_of = t0 + pd.Timedelta(hours=5)
    frames = smc_data_from_store(store, "XAUUSD", as_of, need=("H1",))
    assert len(frames["H1"]) <= 10
    assert frames["H1"]["time"].max() <= as_of


def test_merge_with_resampled_m15() -> None:
    t0 = pd.Timestamp("2025-01-01", tz="UTC")
    m15 = pd.DataFrame(
        {
            "time": [t0 + pd.Timedelta(minutes=15 * i) for i in range(50)],
            "open": [1.0] * 50,
            "high": [1.1] * 50,
            "low": [0.9] * 50,
            "close": [1.0] * 50,
        }
    )
    rs = build_multi_timeframe(m15)
    from_store = {"M15": m15.tail(10)}
    merged = merge_with_resampled_m15(from_store, rs)
    assert "M15" in merged and "H1" in merged and "H4" in merged


def test_simulation_run_step(tmp_path) -> None:
    db = tmp_path / "mtf3.db"
    store = MTFOHLCStore(db)
    rid = store.create_simulation_run("XAUUSD", name="t1", params={"step": 4})
    assert rid >= 1
    store.insert_simulation_step(
        rid,
        pd.Timestamp("2025-06-01", tz="UTC"),
        equity=10_000.0,
        metrics={"trend_bias": "bullish"},
    )
