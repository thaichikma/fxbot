#!/usr/bin/env python3
"""
Giả lập challenge FTMO $10k (2 bước) từ một mốc ngày — tìm kiếm lưới tham số.

Dữ liệu: OHLC M15 tổng hợp (random walk có seed), không phải lịch sử broker thật.
Kết quả: tham chiếu nội bộ (BacktestEngine + ftmo_challenge); không đảm bảo pass challenge thật.

Chạy:
  PYTHONPATH=. uv run python scripts/ftmo_challenge_sim.py --quick
  PYTHONPATH=. uv run python scripts/ftmo_challenge_sim.py --start 2025-01-01 --bars 12000 --seed 7
"""

from __future__ import annotations

import argparse
import copy
import itertools
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

# Tránh hàng nghìn dòng DEBUG từ SMCEngine / lot calc
logger.remove()
logger.add(sys.stderr, level="WARNING")

from backtest.engine import BacktestEngine
from backtest.synthetic_m15 import generate_m15_ohlc

ROOT = Path(__file__).resolve().parent.parent


def _load_settings() -> dict:
    with open(ROOT / "config" / "settings.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_symbols_specs() -> dict:
    with open(ROOT / "config" / "symbols.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("symbols", {})


def _clone_settings(base: dict) -> dict:
    return copy.deepcopy(base)


def run_grid(
    *,
    start: datetime,
    n_bars: int,
    data_seed: int,
    symbol: str,
    initial_balance: float,
    quick: bool = False,
    m15_precomputed: Any | None = None,
) -> list[dict]:
    base = _load_settings()
    specs = _load_symbols_specs()

    m15 = m15_precomputed if m15_precomputed is not None else generate_m15_ohlc(start, n_bars, seed=data_seed)

    if quick:
        risks = [0.0075, 0.01, 0.0125, 0.015]
        step_bars_list = [4, 8]
        swing_lengths = [10, 14]
        fvg_pips = [5, 8]
        costs_flags = [True, False]
    else:
        risks = [0.005, 0.0075, 0.01, 0.0125, 0.015]
        step_bars_list = [2, 4, 8]
        swing_lengths = [8, 10, 14]
        fvg_pips = [3, 5, 8]
        costs_flags = [True, False]

    results: list[dict] = []

    for risk, step, sw, fvg, costs_on in itertools.product(
        risks, step_bars_list, swing_lengths, fvg_pips, costs_flags
    ):
        s = _clone_settings(base)
        s["risk"]["risk_per_trade"] = risk
        s["strategy"]["swing_length"] = sw
        s["strategy"]["fvg_min_size_pips"] = fvg
        s["backtest"]["costs"]["enabled"] = costs_on
        s["backtest"]["initial_balance"] = initial_balance

        eng = BacktestEngine(s, specs)
        r = eng.run(
            symbol,
            m15,
            initial_balance=initial_balance,
            step_bars=step,
            min_m15_bars=120,
            cooldown_bars=8,
        )
        ch = r.challenge or {}
        results.append(
            {
                "risk": risk,
                "step_bars": step,
                "swing_length": sw,
                "fvg_min_size_pips": fvg,
                "costs_enabled": costs_on,
                "final_balance": r.final_balance,
                "profit_usd": r.final_balance - initial_balance,
                "total_return_pct": r.total_return_pct,
                "max_dd_pct": r.max_drawdown_pct,
                "max_daily_loss_pct": r.max_daily_loss_pct,
                "trades": r.total_trades,
                "ftmo_compliant": r.ftmo_compliant,
                "ftmo_fail_reason": r.ftmo_fail_reason or "",
                "final_phase": ch.get("final_phase"),
                "trading_days": ch.get("trading_days"),
                "pass_p2": bool(ch.get("pass_phase2_profit_rule")),
            }
        )

    return results


def main() -> int:
    ap = argparse.ArgumentParser(description="FTMO challenge parameter grid on synthetic M15")
    ap.add_argument("--start", default="2025-01-01", help="UTC start date YYYY-MM-DD")
    ap.add_argument("--bars", type=int, default=12_000, help="Số nến M15 (~96/ngày)")
    ap.add_argument("--seed", type=int, default=42, help="Seed dữ liệu OHLC tổng hợp")
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--balance", type=float, default=10_000.0)
    ap.add_argument(
        "--quick",
        action="store_true",
        help="Lưới nhỏ hơn + mặc định ít nến hơn (chạy nhanh để thử)",
    )
    ap.add_argument(
        "--seed-scan",
        type=int,
        default=0,
        help="Nếu >0: thử nhiều seed dữ liệu 1..N để tìm tổ hợp pass (chậm)",
    )
    args = ap.parse_args()
    if args.quick and args.bars == 12_000:
        args.bars = 6000

    start = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    seed_line = (
        f"seed_scan 1..{args.seed_scan}"
        if args.seed_scan > 0
        else f"seed={args.seed}"
    )
    print(
        f"Giả lập FTMO $10k | bắt đầu {start.date()} UTC | {args.bars} nến M15 | {seed_line}\n"
        f"Symbol={args.symbol} | balance={args.balance} | quick={args.quick}\n"
        "---"
    )

    def _one_grid(seed: int):
        m15 = generate_m15_ohlc(start, args.bars, seed=seed)
        return run_grid(
            start=start,
            n_bars=args.bars,
            data_seed=seed,
            symbol=args.symbol,
            initial_balance=args.balance,
            quick=args.quick,
            m15_precomputed=m15,
        )

    rows: list[dict] = []
    if args.seed_scan > 0:
        for s in range(1, args.seed_scan + 1):
            part = _one_grid(s)
            for p in part:
                p["data_seed"] = s
            rows.extend(part)
    else:
        rows = _one_grid(args.seed)
        for p in rows:
            p["data_seed"] = args.seed

    full_pass = [
        x
        for x in rows
        if x["ftmo_compliant"] and x["final_phase"] == "funded" and x["pass_p2"]
    ]
    phase1_only = [
        x
        for x in rows
        if x["ftmo_compliant"] and x["final_phase"] in ("phase2", "funded")
    ]

    full_pass.sort(key=lambda z: z["profit_usd"], reverse=True)
    phase1_only.sort(key=lambda z: z["profit_usd"], reverse=True)
    rows_by_profit = sorted(rows, key=lambda z: z["profit_usd"], reverse=True)

    print(f"Tổng tổ hợp đã thử: {len(rows)}")
    print(f"FTMO compliant (max DD / daily / best-day): {sum(1 for x in rows if x['ftmo_compliant'])}")

    if full_pass:
        print(f"\n✅ Cấu hình pass heuristic đầy đủ (compliant + funded 15% + ≥4 ngày): {len(full_pass)}")
        for i, x in enumerate(full_pass[:8], 1):
            ds = x.get("data_seed", "")
            sfx = f" data_seed={ds}" if args.seed_scan else ""
            print(
                f"  {i}. profit=${x['profit_usd']:.0f} DD={x['max_dd_pct']:.1f}% "
                f"risk={x['risk']:.3f} step={x['step_bars']} swing={x['swing_length']} "
                f"fvg={x['fvg_min_size_pips']} costs={x['costs_enabled']} trades={x['trades']}{sfx}"
            )
    else:
        print("\n⚠️ Không có tổ hợp nào đạt funded + compliant trên dữ liệu seed này.")

    if not full_pass and phase1_only:
        print(f"\nGợi ý một phần (compliant + ít nhất phase1/phase2 theo lợi nhuận): {len(phase1_only)}")
        for i, x in enumerate(phase1_only[:5], 1):
            print(
                f"  {i}. phase={x['final_phase']} profit=${x['profit_usd']:.0f} "
                f"risk={x['risk']:.3f} step={x['step_bars']} swing={x['swing_length']} "
                f"fvg={x['fvg_min_size_pips']} costs={x['costs_enabled']}"
            )

    print("\n--- Top 5 theo profit (có thể vi phạm FTMO) ---")
    for i, x in enumerate(rows_by_profit[:5], 1):
        print(
            f"  {i}. ${x['profit_usd']:.0f} compliant={x['ftmo_compliant']} phase={x['final_phase']} "
            f"DD={x['max_dd_pct']:.1f}% {x['ftmo_fail_reason'][:60]}"
        )

    # Gợi ý cấu hình YAML nếu có full_pass
    if full_pass:
        best = full_pass[0]
        print("\n--- Gợi ý chỉnh config/settings.yaml (ví dụ tốt nhất trong lưới) ---")
        if args.seed_scan:
            print(f"  # data_seed tổng hợp: {best.get('data_seed')}")
        print(f"  risk.risk_per_trade: {best['risk']}")
        print(f"  strategy.swing_length: {best['swing_length']}")
        print(f"  strategy.fvg_min_size_pips: {best['fvg_min_size_pips']}")
        print(f"  backtest (CLI/Telegram): step_bars={best['step_bars']}  # engine.run step_bars")
        print(f"  backtest.costs.enabled: {best['costs_enabled']}")

    print(
        "\nLưu ý: Dùng dữ liệu tick/candle thật (MT5) và paper trước khi nộp phí challenge."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
