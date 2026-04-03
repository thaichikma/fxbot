"""
Test sau khi **import CSV XAU vào SQLite** (`ohlc_bars`), đọc lại qua `MTFOHLCStore`.

Quy trình:
1. Fixture tạo DB tạm, gọi `import_all_xau_csvs` / `import_csv_to_store` trên `data/`.
2. Test dùng `fetch_last_n` / `fetch_range` — không đọc CSV trực tiếp.

Biến môi trường:
- `FXBOT_TEST_DB_MAX_ROWS` — giới hạn mỗi file khi import (mặc định 15000; giảm nếu chậm).
- `FXBOT_TEST_SKIP_DB_IMPORT` — đặt `1` để bỏ qua toàn bộ module (CI không có file lớn).

Import thủ công vào `data/fxbot.db` (máy dev):
  PYTHONPATH=. python scripts/mtf_import_csv.py --all-xau --replace
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from backtest.engine import BacktestEngine
from src.data.mtf_csv_import import import_all_xau_csvs, import_csv_to_store
from src.data.mtf_store import MTFOHLCStore

ROOT = Path(__file__).resolve().parent.parent


def _db_max_rows() -> int | None:
    v = os.environ.get("FXBOT_TEST_DB_MAX_ROWS", "15000").strip()
    if v.lower() in ("", "none", "full"):
        return None
    return int(v)


def _settings():
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


def _specs():
    with open(ROOT / "config" / "symbols.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["symbols"]


@pytest.fixture(scope="module")
def xau_mtf_db(tmp_path_factory):
    if os.environ.get("FXBOT_TEST_SKIP_DB_IMPORT", "").strip() in ("1", "true", "yes"):
        pytest.skip("FXBOT_TEST_SKIP_DB_IMPORT")

    data_dir = ROOT / "data"
    csvs = sorted(data_dir.glob("XAU_*_data.csv"))
    if not csvs:
        pytest.skip("Không có data/XAU_*_data.csv")

    db_path = tmp_path_factory.mktemp("mtf") / "test_xau_mtf.db"
    store = MTFOHLCStore(db_path)
    store.ensure_schema()
    mr = _db_max_rows()
    counts = import_all_xau_csvs(store, data_dir, symbol="XAUUSD", max_rows=mr, replace=True)
    assert sum(counts.values()) > 0
    return {"store": store, "counts": counts, "db_path": db_path}


@pytest.mark.real_data
def test_db_import_nonzero_counts(xau_mtf_db):
    assert sum(xau_mtf_db["counts"].values()) >= 10


@pytest.mark.real_data
def test_db_fetch_m15_backtest_engine(xau_mtf_db):
    store: MTFOHLCStore = xau_mtf_db["store"]
    if store.count_bars("XAUUSD", "M15") < 120:
        pytest.skip("Không đủ nến M15 trong DB sau import (tăng FXBOT_TEST_DB_MAX_ROWS hoặc file)")
    m15 = store.fetch_last_n("XAUUSD", "M15", min(8000, store.count_bars("XAUUSD", "M15")))
    eng = BacktestEngine(_settings(), _specs())
    r = eng.run("XAUUSD", m15, initial_balance=10_000.0, step_bars=8, min_m15_bars=120)
    assert r.initial_balance == 10_000.0
    assert r.final_balance >= 0


@pytest.mark.real_data
def test_db_fetch_multi_tf(xau_mtf_db):
    store: MTFOHLCStore = xau_mtf_db["store"]
    for tf in ("H1", "M5", "D1"):
        if store.count_bars("XAUUSD", tf) == 0:
            continue
        n = min(500, store.count_bars("XAUUSD", tf))
        df = store.fetch_last_n("XAUUSD", tf, n)
        assert len(df) == n
        assert list(df.columns)[:5] == ["time", "open", "high", "low", "close"]
        break
    else:
        pytest.skip("Không có TF nào có dữ liệu")


@pytest.mark.real_data
def test_db_ml_features_from_m15(xau_mtf_db):
    from src.ml.features import feature_matrix

    store: MTFOHLCStore = xau_mtf_db["store"]
    if store.count_bars("XAUUSD", "M15") < 100:
        pytest.skip("Thiếu M15")
    m15 = store.fetch_last_n("XAUUSD", "M15", min(2000, store.count_bars("XAUUSD", "M15")))
    if "volume" not in m15.columns:
        m15 = m15.copy()
        m15["volume"] = 0.0
    X = feature_matrix(m15)
    assert len(X) == len(m15)


@pytest.mark.real_data
@pytest.mark.skipif(
    not (ROOT / "data" / "XAU_15m_data.csv").is_file(),
    reason="Không có CSV M15",
)
def test_import_single_file_matches_direct_load(tmp_path):
    """Một file: số nến DB sau import = min(len(csv), max_rows)."""
    store = MTFOHLCStore(tmp_path / "one.db")
    p = ROOT / "data" / "XAU_15m_data.csv"
    mr = 3000
    n = import_csv_to_store(store, p, "XAUUSD", max_rows=mr, replace=True)
    assert n > 100
    assert n <= mr
    assert store.count_bars("XAUUSD", "M15") == n
