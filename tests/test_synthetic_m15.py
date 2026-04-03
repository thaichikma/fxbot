"""Synthetic M15 generation for FTMO sim / grid search."""

from __future__ import annotations

from datetime import datetime, timezone

from backtest.synthetic_m15 import generate_m15_ohlc


def test_generate_m15_shape_and_start() -> None:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    df = generate_m15_ohlc(start, 100, seed=1)
    assert len(df) == 100
    assert list(df.columns) == ["time", "open", "high", "low", "close"]
    assert str(df.iloc[0]["time"].date()) == "2025-01-01"
