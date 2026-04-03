"""Tests for backtest.mt5_fetch helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from backtest.mt5_fetch import fetch_m15_to_csv, looks_like_csv_path
from src.core.mt5_mock import MT5Mock


def test_looks_like_csv_path() -> None:
    assert looks_like_csv_path("data/backtest/foo.csv") is True
    assert looks_like_csv_path("data\\backtest\\x.csv") is True
    assert looks_like_csv_path("XAUUSD") is False
    assert looks_like_csv_path("EURUSD") is False


def test_fetch_m15_to_csv_mock(tmp_path: Path) -> None:
    m = MT5Mock()
    m.initialize()
    out = tmp_path / "t.csv"
    n = fetch_m15_to_csv(m, "EURUSD", out, 50)
    assert n == 50
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert "time" in text and "open" in text


def test_fetch_m15_disconnected_mt5_client(tmp_path: Path) -> None:
    from src.core.mt5_client import MT5Client

    c = MT5Client()
    out = tmp_path / "x.csv"
    with pytest.raises(RuntimeError):
        fetch_m15_to_csv(c, "EURUSD", out, 10)
