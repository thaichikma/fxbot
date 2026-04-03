"""
Test trên DataFrame đọc từ CSV thật (file bạn đặt trong `data/`).

- Luôn chạy: `data/backtest/sample_m15.csv` (có trong repo).
- Tùy chọn: `data/XAU_15m_data.csv`, `data/XAU_1d_data.csv` — skip nếu không có file.

Biến môi trường:
- `FXBOT_TEST_MAX_BARS` — giới hạn số nến sau khi load (mặc định 8000; giảm nếu cần nhanh).
- `FXBOT_TEST_CSV` — đường dẫn tuyệt đối hoặc tương đối project tới một CSV tùy chỉnh.
- `FXBOT_TEST_SYMBOL` — ký hiệu cho engine (mặc định suy ra từ tên file hoặc EURUSD).

Chạy chỉ nhóm này:
  pytest tests/test_real_data_csv.py -m real_data
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from backtest.data_loader import load_ohlc_csv, slice_ohlc_by_window
from backtest.engine import BacktestEngine

ROOT = Path(__file__).resolve().parent.parent


def _specs() -> dict:
    with open(ROOT / "config" / "symbols.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["symbols"]


def _settings() -> dict:
    return {
        "risk": {"risk_per_trade": 0.01},
        "strategy": {
            "fvg_min_size_pips": 3,
            "sl_buffer_pips": 5,
            "tp_ratios": [1.5, 2.0, 3.0],
            "signal_expiry_minutes": 60,
            "max_signals_per_scan_per_symbol": 2,
        },
    }


def _max_bars() -> int:
    return int(os.environ.get("FXBOT_TEST_MAX_BARS", "8000"))


def _resolve_csv_path(rel_or_abs: str) -> Path:
    p = Path(rel_or_abs)
    if not p.is_absolute():
        p = ROOT / p
    return p.resolve()


@pytest.mark.real_data
def test_real_sample_m15_csv_always_present():
    """EURUSD-style sample — file nhỏ, luôn có trong repo."""
    p = ROOT / "data" / "backtest" / "sample_m15.csv"
    assert p.is_file(), "Thiếu data/backtest/sample_m15.csv"
    df = load_ohlc_csv(p)
    assert len(df) >= 50
    assert set(df.columns) >= {"time", "open", "high", "low", "close"}


@pytest.mark.real_data
def test_real_sample_m15_backtest_engine():
    p = ROOT / "data" / "backtest" / "sample_m15.csv"
    assert p.is_file()
    df = load_ohlc_csv(p)
    eng = BacktestEngine(_settings(), _specs())
    r = eng.run("EURUSD", df, initial_balance=10_000.0, step_bars=4, min_m15_bars=80)
    assert r.initial_balance == 10_000.0
    assert r.final_balance >= 0
    assert r.total_trades >= 0


@pytest.mark.real_data
@pytest.mark.skipif(
    not (ROOT / "data" / "XAU_15m_data.csv").is_file(),
    reason="Thêm data/XAU_15m_data.csv để chạy (file lớn, tùy chọn).",
)
def test_real_xau_15m_backtest_slice():
    p = ROOT / "data" / "XAU_15m_data.csv"
    df = load_ohlc_csv(p)
    assert len(df) > 500
    slim = slice_ohlc_by_window(df, max_bars=_max_bars(), tail=True)
    eng = BacktestEngine(_settings(), _specs())
    r = eng.run("XAUUSD", slim, initial_balance=10_000.0, step_bars=8, min_m15_bars=120)
    assert r.initial_balance == 10_000.0
    assert r.final_balance >= 0


@pytest.mark.real_data
@pytest.mark.skipif(
    not (ROOT / "data" / "XAU_1d_data.csv").is_file(),
    reason="Thêm data/XAU_1d_data.csv để chạy (tùy chọn).",
)
def test_real_xau_1d_load_and_smoke():
    """D1 không phải M15 — chỉ kiểm tra load + slice; không ép chạy engine M15 (sẽ fail ít bar)."""
    p = ROOT / "data" / "XAU_1d_data.csv"
    df = load_ohlc_csv(p)
    assert len(df) > 10
    slim = slice_ohlc_by_window(df, max_bars=min(500, len(df)), tail=True)
    assert len(slim) >= 10


@pytest.mark.real_data
@pytest.mark.skipif(
    not os.environ.get("FXBOT_TEST_CSV", "").strip(),
    reason="Đặt FXBOT_TEST_CSV=/path/to/file.csv (hoặc data/...) để test file bạn cung cấp.",
)
def test_real_user_provided_csv_env():
    """CSV tùy chỉnh bạn chỉ định qua biến môi trường."""
    raw = os.environ["FXBOT_TEST_CSV"].strip()
    p = _resolve_csv_path(raw)
    assert p.is_file(), f"Không tìm thấy file: {p}"

    sym = os.environ.get("FXBOT_TEST_SYMBOL", "").strip().upper()
    if not sym:
        name = p.name.upper()
        if "XAU" in name:
            sym = "XAUUSD"
        elif "EUR" in name:
            sym = "EURUSD"
        else:
            sym = "XAUUSD"

    df = load_ohlc_csv(p)
    assert len(df) > 100
    slim = slice_ohlc_by_window(df, max_bars=min(_max_bars(), len(df)), tail=True)
    eng = BacktestEngine(_settings(), _specs())
    r = eng.run(sym, slim, initial_balance=10_000.0, step_bars=8, min_m15_bars=120)
    assert r.initial_balance == 10_000.0
    assert r.final_balance >= 0


@pytest.mark.real_data
@pytest.mark.skipif(
    not (ROOT / "data" / "XAU_15m_data.csv").is_file(),
    reason="Thêm data/XAU_15m_data.csv.",
)
def test_real_xau_ml_features_smoke():
    """Đặc trưng ML (RSI/ATR/volume) trên slice thật — không cần train."""
    from src.ml.features import feature_matrix

    p = ROOT / "data" / "XAU_15m_data.csv"
    df = load_ohlc_csv(p)
    slim = slice_ohlc_by_window(df, max_bars=min(2000, len(df)), tail=True)
    # thêm volume giả nếu CSV không có (MT4 có Volume)
    if "tick_volume" not in slim.columns and "volume" not in slim.columns:
        slim = slim.copy()
        slim["tick_volume"] = 1000.0
    X = feature_matrix(slim)
    assert len(X) == len(slim)
    assert not X.isna().any().any()
