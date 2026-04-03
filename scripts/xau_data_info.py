#!/usr/bin/env python3
"""
Thống kê nhanh các file data/XAU_*.csv (MT4 export) — không đọc hết file lớn (1m/5m).

Chạy từ thư mục gốc repo:
  PYTHONPATH=. uv run python scripts/xau_data_info.py

Để kiểm tra parse đầy đủ một file nhỏ (hoặc slice) dùng backtest CLI / pytest.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _line_count(path: Path) -> int:
    out = subprocess.check_output(["wc", "-l", str(path)], text=True)
    return max(0, int(out.split()[0]) - 1)


def _first_last_data_lines(path: Path) -> tuple[str, str]:
    """Dòng dữ liệu đầu và cuối (bỏ header)."""
    head = subprocess.check_output(["head", "-n", "2", str(path)], text=True)
    lines = [ln for ln in head.splitlines() if ln.strip()]
    first_data = lines[1] if len(lines) > 1 else ""
    last = subprocess.check_output(["tail", "-n", "1", str(path)], text=True).strip()
    return first_data, last


def _date_field(line: str) -> str:
    if not line:
        return ""
    return line.split(";")[0].split(",")[0].strip()


def main() -> int:
    data = ROOT / "data"
    if not data.is_dir():
        print("Không thấy thư mục data/", file=sys.stderr)
        return 1
    files = sorted(data.glob("XAU_*.csv"))
    if not files:
        print("Không có file data/XAU_*.csv")
        return 0
    for f in files:
        try:
            n = _line_count(f)
            first, last = _first_last_data_lines(f)
            d0, d1 = _date_field(first), _date_field(last)
            print(f"{f.name}\trows≈{n}\t{d0} .. {d1}", flush=True)
        except Exception as e:
            print(f"{f.name}\tERROR: {e}", flush=True)
    print(
        "\nBacktest dùng **M15** (engine tự ghép H1/H4 từ M15). Các TF khác: tham chiếu / kiểm chứng ngoài.",
        flush=True,
    )
    print(
        "  PYTHONPATH=. python -m backtest --symbol XAUUSD --csv data/XAU_15m_data.csv "
        "--max-bars 50000 --step 4",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
