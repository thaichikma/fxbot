"""Tests for ML feature builder."""

from datetime import datetime, timezone

import pandas as pd

from src.ml.features import build_features, feature_matrix


def test_feature_matrix_shape():
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    n = 100
    df = pd.DataFrame(
        {
            "time": [t0 + pd.Timedelta(hours=i) for i in range(n)],
            "open": [1.0 + i * 0.0001 for i in range(n)],
            "high": [1.0 + i * 0.0001 + 0.0002 for i in range(n)],
            "low": [1.0 + i * 0.0001 - 0.0001 for i in range(n)],
            "close": [1.0 + i * 0.0001 for i in range(n)],
            "tick_volume": [1000 + i for i in range(n)],
        }
    )
    X = feature_matrix(df)
    assert len(X) == n
    assert list(X.columns) == ["ret_1", "rsi_14", "atr_14", "log_vol", "hl_range"]
    assert not X.isna().any().any()


def test_build_features_no_crash():
    df = pd.DataFrame(
        {
            "time": pd.date_range("2025-01-01", periods=50, freq="h", tz="UTC"),
            "open": 1.0,
            "high": 1.01,
            "low": 0.99,
            "close": 1.0,
        }
    )
    b = build_features(df)
    assert len(b) == 50
