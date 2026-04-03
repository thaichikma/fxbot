"""
Sinh chuỗi OHLC M15 từ mốc thời gian (UTC) — dùng giả lập backtest / tối ưu tham số.

Không phải dữ liệu thị trường thật; random walk có seed để lặp lại được.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd


def generate_m15_ohlc(
    start: datetime,
    n_bars: int,
    *,
    base_price: float = 1.0850,
    pip_size: float = 0.0001,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Tạo `n_bars` nến M15 bắt đầu từ `start` (UTC).

    Giá dùng random walk Gaussian (tương tự MT5Mock cho forex).
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    else:
        start = start.astimezone(timezone.utc)

    rng = np.random.default_rng(seed)
    returns = rng.normal(0, pip_size * 5, n_bars)
    prices = base_price + np.cumsum(returns)

    rows = []
    for i in range(n_bars):
        bar_time = start + timedelta(minutes=15 * i)
        o = float(prices[i])
        noise = abs(rng.normal(0, pip_size * 10))
        h = o + noise
        l = o - noise
        c = o + rng.normal(0, pip_size * 3)
        hi = max(o, h, c)
        lo = min(o, l, c)
        rows.append(
            {
                "time": bar_time,
                "open": round(o, 5),
                "high": round(hi, 5),
                "low": round(lo, 5),
                "close": round(c, 5),
            }
        )

    return pd.DataFrame(rows)
