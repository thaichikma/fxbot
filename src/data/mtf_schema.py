"""
Schema SQLite — OHLC đa khung (MTF) + bản ghi giả lập (simulation).

Dùng chung file `data/fxbot.db` với `Database` hoặc file riêng qua MTFOHLCStore(path).
"""

from __future__ import annotations

# Nến OHLC theo symbol + khung (M1 … MN1); ts ISO UTC.
MTF_OHLC_SCHEMA = """
CREATE TABLE IF NOT EXISTS ohlc_bars (
    symbol TEXT NOT NULL,
    tf TEXT NOT NULL,
    ts TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL,
    source TEXT,
    PRIMARY KEY (symbol, tf, ts)
);

CREATE INDEX IF NOT EXISTS idx_ohlc_symbol_tf_ts_desc ON ohlc_bars(symbol, tf, ts DESC);
"""

# Phiên giả lập / walk-forward (tùy chọn ghi metrics theo nến).
SIMULATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS simulation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    symbol TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    params_json TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS simulation_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    bar_ts TEXT NOT NULL,
    ref_tf TEXT DEFAULT 'M15',
    equity REAL,
    balance REAL,
    metrics_json TEXT,
    FOREIGN KEY (run_id) REFERENCES simulation_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_sim_steps_run_ts ON simulation_steps(run_id, bar_ts);
"""

MTF_FULL_SCHEMA = MTF_OHLC_SCHEMA + SIMULATION_SCHEMA

# Map tên file CSV (hậu tố) → mã TF trong DB
CSV_SUFFIX_TO_TF: dict[str, str] = {
    "1m_data": "M1",
    "5m_data": "M5",
    "15m_data": "M15",
    "30m_data": "M30",
    "1h_data": "H1",
    "4h_data": "H4",
    "1d_data": "D1",
    "1w_data": "W1",
    "1Month_data": "MN1",
}
