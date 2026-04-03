"""Loader MT4-style semicolon + Date với dấu chấm."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from backtest.data_loader import load_ohlc_csv, slice_ohlc_by_window


def test_load_mt4_semicolon_dot_date(tmp_path: Path) -> None:
    p = tmp_path / "xau.csv"
    p.write_text(
        "Date;Open;High;Low;Close;Volume\n"
        "2004.06.11 07:15;384;384.3;383.8;384.3;12\n"
        "2004.06.11 07:30;383.8;384;383.6;383.8;20\n",
        encoding="utf-8",
    )
    df = load_ohlc_csv(p)
    assert len(df) == 2
    assert df["close"].iloc[0] == pytest.approx(384.3)
    assert str(df["time"].iloc[0].date()) == "2004-06-11"


def test_slice_to_date_inclusive_day() -> None:
    t0 = pd.Timestamp("2025-01-01", tz="UTC")
    rows = []
    for i in range(3):
        rows.append(
            {
                "time": t0 + pd.Timedelta(hours=12 * i),
                "open": 1.0,
                "high": 1.1,
                "low": 0.9,
                "close": 1.0,
            }
        )
    df = pd.DataFrame(rows)
    s = slice_ohlc_by_window(df, to_date="2025-01-01")
    assert len(s) == 2


def test_slice_max_bars_tail() -> None:
    t0 = pd.Timestamp("2020-01-01", tz="UTC")
    rows = [{"time": t0 + pd.Timedelta(minutes=15 * i), "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0} for i in range(10)]
    df = pd.DataFrame(rows)
    s = slice_ohlc_by_window(df, max_bars=3, tail=True)
    assert len(s) == 3
    assert s["time"].iloc[0] == df["time"].iloc[7]


@pytest.mark.skipif(
    not (Path(__file__).resolve().parent.parent / "data" / "XAU_15m_data.csv").is_file(),
    reason="Local XAU CSV not present",
)
def test_load_real_xau_15m_smoke() -> None:
    root = Path(__file__).resolve().parent.parent
    df = load_ohlc_csv(root / "data" / "XAU_15m_data.csv")
    assert len(df) > 1000
    slim = slice_ohlc_by_window(df, max_bars=500, tail=True)
    assert len(slim) == 500
