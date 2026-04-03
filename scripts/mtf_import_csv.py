#!/usr/bin/env python3
"""
Nạp CSV MT4 (data/XAU_*_data.csv) vào SQLite — bảng ohlc_bars (đa khung).

Mặc định dùng data/fxbot.db (cùng bot). Có thể chỉ định file khác.

Ví dụ:
  PYTHONPATH=. uv run python scripts/mtf_import_csv.py --symbol XAUUSD \\
    data/XAU_15m_data.csv data/XAU_1h_data.csv

  PYTHONPATH=. uv run python scripts/mtf_import_csv.py --all-xau --max-rows 5000000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loguru import logger

logger.remove()
logger.add(sys.stderr, level="INFO")

from src.data.mtf_csv_import import glob_default_xau_csvs, import_csv_to_store, infer_tf_from_filename
from src.data.mtf_store import MTFOHLCStore


def infer_tf(path: Path) -> str:
    return infer_tf_from_filename(path)


def main() -> int:
    ap = argparse.ArgumentParser(description="Import MT4 OHLC CSV vào SQLite (ohlc_bars)")
    ap.add_argument("--db", default="data/fxbot.db", help="Đường dẫn SQLite")
    ap.add_argument("--symbol", default="XAUUSD", help="Symbol")
    ap.add_argument("--replace", action="store_true", help="Ghi đè nếu trùng (symbol,tf,ts)")
    ap.add_argument("--max-rows", type=int, default=None, help="Chỉ giữ N nến cuối sau khi lọc")
    ap.add_argument(
        "--all-xau",
        action="store_true",
        help="Nạp mọi data/XAU_*_data.csv trong thư mục data/",
    )
    ap.add_argument("paths", nargs="*", help="File CSV (nếu không dùng --all-xau)")
    args = ap.parse_args()

    store = MTFOHLCStore(ROOT / args.db)
    store.ensure_schema()

    if args.all_xau:
        paths = glob_default_xau_csvs(ROOT / "data")
        if not paths:
            print("Không tìm thấy data/XAU_*_data.csv", file=sys.stderr)
            return 1
    else:
        paths = [ROOT / p for p in args.paths]
        if not paths:
            ap.print_help()
            return 1

    total = 0
    for p in paths:
        p = Path(p).resolve()
        if not p.is_file():
            print(f"Thiếu file: {p}", file=sys.stderr)
            return 1
        tf = infer_tf(p)
        print(f"→ {p.name} | TF={tf} | đọc CSV...", flush=True)
        n = import_csv_to_store(
            store,
            p,
            args.symbol,
            max_rows=args.max_rows,
            replace=args.replace,
        )
        total += n
        print(f"   Đã ghi {n} nến", flush=True)

    print(f"Xong. Tổng dòng chèn: {total} | DB: {store.db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
