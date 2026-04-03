"""
Feature matrix cho ML: RSI, ATR, Volume (log-scaled), returns.

Dùng với `train_xgb.py` / `train_lstm.py` hoặc inference trong `ml_engine`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.ml.indicators import atr, rsi, volume_column

FEATURE_COLUMNS = ("ret_1", "rsi_14", "atr_14", "log_vol", "hl_range")


def _returns(close: pd.Series) -> pd.Series:
    return close.pct_change().fillna(0.0)


def feature_matrix(ohlc: pd.DataFrame) -> pd.DataFrame:
    """Ma trận đặc trưng theo đúng thứ tự cột (train/inference)."""
    return build_features(ohlc)[list(FEATURE_COLUMNS)]


def build_features(ohlc: pd.DataFrame) -> pd.DataFrame:
    """
    `ohlc`: cột time, open, high, low, close; tùy chọn tick_volume/volume.
    """
    df = ohlc.sort_values("time").reset_index(drop=True)
    c = df["close"].astype(float)
    vol = volume_column(df)
    log_vol = np.log1p(vol.clip(lower=0.0))
    hl = ((df["high"] - df["low"]) / c.replace(0.0, np.nan)).fillna(0.0)
    out = pd.DataFrame(
        {
            "ret_1": _returns(c),
            "rsi_14": rsi(c, 14),
            "atr_14": atr(df, 14) / c.replace(0.0, np.nan),
            "log_vol": log_vol,
            "hl_range": hl,
        },
        index=df.index,
    )
    return out.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def build_labels_forward_return(close: pd.Series, horizon: int = 5) -> pd.Series:
    """Nhãn nhị phân: giá sau `horizon` nến > hiện tại."""
    f = close.shift(-horizon)
    return (f > close).astype(int)
