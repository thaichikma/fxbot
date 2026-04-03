"""
Tải nến M15 từ MT5Client (terminal thật hoặc MT5Mock) và ghi CSV cho backtest.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger


def fetch_m15_to_csv(mt5_client: Any, symbol: str, out_path: Path, count: int) -> int:
    """
    Lấy OHLC M15 qua get_rates, ghi CSV (time, open, high, low, close).

    Returns:
        Số nến đã ghi.

    Raises:
        RuntimeError: không có dữ liệu hoặc thiếu cột.
    """
    sym = symbol.upper()
    if hasattr(mt5_client, "ensure_symbol_ready"):
        mt5_client.ensure_symbol_ready(sym)

    df = mt5_client.get_rates(sym, "M15", count)
    if df is None or len(df) == 0:
        raise RuntimeError(f"Không lấy được M15 cho {sym} (kiểm tra symbol trong Market Watch / mock).")

    cols = ["time", "open", "high", "low", "close"]
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise RuntimeError(f"Thiếu cột: {missing}")

    out = df[cols].copy()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)
    logger.info("Backtest CSV saved | {} | {} bars | {}", sym, len(out), out_path)
    return len(out)


def looks_like_csv_path(arg: str) -> bool:
    """True nếu đối số trông như đường dẫn file .csv."""
    a = arg.strip()
    if not a:
        return False
    if ".csv" in a.lower():
        return True
    if "/" in a or "\\" in a:
        return True
    return False
