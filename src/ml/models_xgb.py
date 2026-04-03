"""Huấn luyện / dự báo XGBoost (optional dependency)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.ml.features import build_labels_forward_return, feature_matrix


def _require_xgb():
    try:
        import xgboost as xgb  # noqa: F401
    except ImportError as e:
        raise ImportError("Cài xgboost: pip install xgboost (hoặc pip install -r requirements-ml.txt)") from e
    import xgboost as xgb

    return xgb


def train_xgb_classifier(
    ohlc: pd.DataFrame,
    *,
    horizon: int = 5,
    test_ratio: float = 0.2,
    **xgb_params: Any,
) -> tuple[Any, dict[str, float]]:
    """
    Train binary classifier P(up).
    Trả về (model, metrics dict).
    """
    xgb = _require_xgb()
    X = feature_matrix(ohlc)
    y = build_labels_forward_return(ohlc["close"].astype(float), horizon=horizon)
    valid = y.notna()
    X = X.loc[valid].values
    y = y.loc[valid].astype(int).values
    n = len(X)
    if n < 50:
        raise ValueError("Cần ít nhất ~50 mẫu sau khi lọc nhãn.")

    split = int(n * (1.0 - test_ratio))
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    params = {
        "max_depth": 4,
        "learning_rate": 0.05,
        "n_estimators": 200,
        "subsample": 0.8,
        "objective": "binary:logistic",
        "eval_metric": "logloss",
    }
    params.update(xgb_params)

    clf = xgb.XGBClassifier(**params)
    clf.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

    proba = clf.predict_proba(X_test)[:, 1]
    pred = (proba >= 0.5).astype(int)
    acc = float((pred == y_test).mean()) if len(y_test) else 0.0
    metrics = {"accuracy": acc, "n_train": float(len(y_train)), "n_test": float(len(y_test))}
    return clf, metrics


def predict_proba_up(model: Any, ohlc_last_window: pd.DataFrame) -> float:
    """Xác suất hướng lên từ vài nến cuối."""
    X = feature_matrix(ohlc_last_window)
    row = X.iloc[-1:].values
    return float(model.predict_proba(row)[0, 1])


def save_xgb(model: Any, path: str | Path) -> None:
    import pickle

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(model, f)


def load_xgb(path: str | Path) -> Any:
    import pickle

    with open(path, "rb") as f:
        return pickle.load(f)
