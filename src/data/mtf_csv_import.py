"""
Import CSV MT4/MT5 (data/XAU_*_data.csv) vào MTFOHLCStore — dùng từ CLI và pytest.
"""

from __future__ import annotations

from pathlib import Path

from backtest.data_loader import load_ohlc_csv, slice_ohlc_by_window
from src.data.mtf_schema import CSV_SUFFIX_TO_TF
from src.data.mtf_store import MTFOHLCStore


def infer_tf_from_filename(path: Path) -> str:
    stem = path.stem.lower()
    # Hậu tố dài trước (tránh "5m_data" khớp trong "xau_15m_data").
    items = sorted(CSV_SUFFIX_TO_TF.items(), key=lambda x: len(x[0]), reverse=True)
    for suffix, tf in items:
        if suffix.lower() in stem:
            return tf
    raise ValueError(
        f"Không map được TF từ {path.name}. Kỳ vọng hậu tố một trong: {list(CSV_SUFFIX_TO_TF.keys())}",
    )


def import_csv_to_store(
    store: MTFOHLCStore,
    csv_path: str | Path,
    symbol: str,
    *,
    max_rows: int | None = None,
    replace: bool = False,
) -> int:
    """
    Đọc CSV (chuẩn hóa OHLC [+volume]), map TF từ tên file, chèn vào `ohlc_bars`.
    """
    p = Path(csv_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(p)
    tf = infer_tf_from_filename(p)
    df = load_ohlc_csv(p)
    if max_rows is not None and len(df) > max_rows:
        df = slice_ohlc_by_window(df, max_bars=max_rows, tail=True)
    return store.insert_dataframe(df, symbol, tf, source=p.name, replace=replace)


def glob_default_xau_csvs(data_dir: str | Path) -> list[Path]:
    """Mọi `data/XAU_*_data.csv` sắp xếp theo tên."""
    d = Path(data_dir)
    return sorted(d.glob("XAU_*_data.csv"))


def import_all_xau_csvs(
    store: MTFOHLCStore,
    data_dir: str | Path,
    symbol: str = "XAUUSD",
    *,
    max_rows: int | None = None,
    replace: bool = False,
) -> dict[str, int]:
    """
    Nạp tất cả file khớp pattern; trả về {filename: số dòng chèn}.
    """
    counts: dict[str, int] = {}
    for p in glob_default_xau_csvs(data_dir):
        n = import_csv_to_store(store, p, symbol, max_rows=max_rows, replace=replace)
        counts[p.name] = n
    return counts
