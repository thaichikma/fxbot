"""
CLI: python -m backtest --symbol EURUSD --csv path/to/m15.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from backtest.data_loader import load_ohlc_csv, slice_ohlc_by_window
from backtest.engine import BacktestEngine
from backtest.paper import paper_trading_summary
from backtest.reporter import BacktestReporter


def _load_yaml(project_root: Path, name: str) -> dict:
    p = project_root / "config" / name
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_backtest_report(
    project_root: Path | str,
    *,
    symbol: str,
    csv: str | Path,
    balance: float = 10_000.0,
    step_bars: int = 4,
    min_m15_bars: int = 120,
    include_paper_summary: bool = True,
    from_date: str | None = None,
    to_date: str | None = None,
    max_bars: int | None = None,
    m1_csv: str | Path | None = None,
    max_m15_bars_for_exit: int = 96,
) -> str:
    """
    Chạy backtest và trả về chuỗi báo cáo (dùng cho CLI và Telegram).

    `csv` có thể là đường dẫn tuyệt đối hoặc tương đối theo `project_root`.
    Hỗ trợ CSV MT4 (`Date;Open;High;Low;Close;Volume`) qua `load_ohlc_csv`.

    `from_date` / `to_date`: ISO `YYYY-MM-DD` (UTC). `max_bars`: giữ tối đa N nến cuối sau khi lọc.
    `m1_csv`: nếu có — đánh giá SL/TP trên M1; entry SMC vẫn trên M15.
    """
    root = Path(project_root).resolve()
    csv_path = Path(csv)
    if not csv_path.is_absolute():
        csv_path = root / csv_path
    if not csv_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy CSV: {csv_path}")

    settings = _load_yaml(root, "settings.yaml")
    symbols_yaml = _load_yaml(root, "symbols.yaml")
    specs = symbols_yaml.get("symbols", {})

    m15 = load_ohlc_csv(csv_path)
    m15 = slice_ohlc_by_window(
        m15,
        from_date=from_date,
        to_date=to_date,
        max_bars=max_bars,
        tail=True,
    )

    m1_df = None
    bt = settings.get("backtest", {}) or {}
    m1_path = m1_csv or bt.get("m1_csv") or ""
    if str(m1_path).strip():
        m1p = Path(m1_path)
        if not m1p.is_absolute():
            m1p = root / m1p
        if m1p.is_file():
            m1_df = load_ohlc_csv(m1p)
            m1_df = slice_ohlc_by_window(
                m1_df,
                from_date=from_date,
                to_date=to_date,
                max_bars=None,
                tail=True,
            )
            if len(m15) and len(m1_df):
                t0, t1 = m15["time"].min(), m15["time"].max()
                m1_df = m1_df[(m1_df["time"] >= t0) & (m1_df["time"] <= t1)].reset_index(drop=True)

    engine = BacktestEngine(settings, specs)
    result = engine.run(
        symbol,
        m15,
        initial_balance=balance,
        step_bars=step_bars,
        min_m15_bars=min_m15_bars,
        m1=m1_df,
        max_m15_bars_for_exit=max_m15_bars_for_exit,
    )

    rep = BacktestReporter()
    parts = [rep.generate_plain(result)]
    if include_paper_summary:
        parts.extend(["", paper_trading_summary()])
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FXBot backtest (M15 CSV → SMC + FTMO metrics)")
    parser.add_argument("--symbol", default="EURUSD", help="Symbol name (for specs)")
    parser.add_argument("--csv", required=True, help="Path to M15 OHLCV CSV")
    parser.add_argument("--balance", type=float, default=10_000.0, help="Initial balance")
    parser.add_argument("--step", type=int, default=4, help="M15 bars between SMC evaluations")
    parser.add_argument("--min-bars", type=int, default=120, help="Minimum M15 bars required")
    parser.add_argument("--from-date", dest="from_date", default=None, help="Lọc từ ngày ISO YYYY-MM-DD (UTC)")
    parser.add_argument("--to-date", dest="to_date", default=None, help="Lọc đến ngày ISO YYYY-MM-DD (UTC)")
    parser.add_argument("--max-bars", dest="max_bars", type=int, default=None, help="Giữ tối đa N nến cuối (sau lọc)")
    parser.add_argument(
        "--m1-csv",
        dest="m1_csv",
        default=None,
        help="CSV M1: mô phỏng exit trên M1 (entry SMC vẫn M15). Mặc định: backtest.m1_csv trong settings",
    )
    parser.add_argument(
        "--max-m15-exit",
        dest="max_m15_exit",
        type=int,
        default=96,
        help="Giới hạn chờ lệnh theo quy mô M15 (×15 nến M1)",
    )
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parent.parent
    text = run_backtest_report(
        root,
        symbol=args.symbol,
        csv=args.csv,
        balance=args.balance,
        step_bars=args.step,
        min_m15_bars=args.min_bars,
        include_paper_summary=True,
        from_date=args.from_date,
        to_date=args.to_date,
        max_bars=args.max_bars,
        m1_csv=args.m1_csv,
        max_m15_bars_for_exit=args.max_m15_exit,
    )
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
