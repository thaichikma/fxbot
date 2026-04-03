"""
Giả lập / walk-forward với dữ liệu đa khung từ `MTFOHLCStore`.

`SMCEngine.analyze` cần `data = {"H4": df, "H1": df, "M15": df}` — lấy từ DB thay vì
resample một mình M15 khi đã có nến native từng TF.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.data.mtf_store import MTFOHLCStore


def smc_data_from_store(
    store: MTFOHLCStore,
    symbol: str,
    as_of: pd.Timestamp | str,
    *,
    need: tuple[str, ...] = ("H4", "H1", "M15"),
    min_rows: dict[str, int] | None = None,
) -> dict[str, pd.DataFrame]:
    """
    Trả dict khung hợp tên SMCEngine (H4, H1, M15, …) — chỉ nến ≤ `as_of`.

    Khi thiếu TF trong DB (vd. chỉ import M15), có thể kết hợp với
    `backtest.data_loader.build_multi_timeframe` từ M15.
    """
    return store.frames_up_to(symbol, as_of, need=need, min_rows=min_rows or {})


def merge_with_resampled_m15(
    from_store: dict[str, pd.DataFrame],
    m15_from_resample: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    """
    Ưu tiên DataFrame từ DB nếu đủ dòng; không thì dùng bản resample từ M15.
    """
    out: dict[str, pd.DataFrame] = {}
    all_tf = set(from_store.keys()) | set(m15_from_resample.keys())
    for tf in all_tf:
        db_df = from_store.get(tf)
        if db_df is not None and len(db_df) >= 5:
            out[tf] = db_df
        elif tf in m15_from_resample:
            out[tf] = m15_from_resample[tf]
    return out


def record_step_metrics(
    store: MTFOHLCStore,
    run_id: int,
    bar_ts: pd.Timestamp,
    *,
    equity: float | None = None,
    balance: float | None = None,
    metrics: dict[str, Any] | None = None,
    ref_tf: str = "M15",
) -> None:
    """Ghi một bước giả lập (equity, metrics JSON: trend, ADX, …)."""
    store.insert_simulation_step(
        run_id,
        bar_ts,
        ref_tf=ref_tf,
        equity=equity,
        balance=balance,
        metrics=metrics,
    )
