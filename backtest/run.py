"""
CLI: python -m backtest --symbol EURUSD --csv path/to/m15.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from backtest.data_loader import load_ohlc_csv
from backtest.engine import BacktestEngine
from backtest.paper import paper_trading_summary
from backtest.reporter import BacktestReporter


def _load_yaml(project_root: Path, name: str) -> dict:
    p = project_root / "config" / name
    with open(p) as f:
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
) -> str:
    """
    Chạy backtest và trả về chuỗi báo cáo (dùng cho CLI và Telegram).

    `csv` có thể là đường dẫn tuyệt đối hoặc tương đối theo `project_root`.
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
    engine = BacktestEngine(settings, specs)
    result = engine.run(
        symbol,
        m15,
        initial_balance=balance,
        step_bars=step_bars,
        min_m15_bars=min_m15_bars,
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
    )
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
