"""LSTM nhị phân (PyTorch) — optional dependency."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.ml.features import build_labels_forward_return, feature_matrix


def _torch():
    try:
        import torch
        import torch.nn as nn
    except ImportError as e:
        raise ImportError("Cài torch: pip install torch (hoặc requirements-ml.txt)") from e
    return torch, nn


def _sequences(X: np.ndarray, y: np.ndarray, seq_len: int) -> tuple[np.ndarray, np.ndarray]:
    xs, ys = [], []
    for i in range(len(X) - seq_len):
        xs.append(X[i : i + seq_len])
        ys.append(y[i + seq_len - 1])
    return np.stack(xs, dtype=np.float32), np.array(ys, dtype=np.float32)


def train_lstm_classifier(
    ohlc: pd.DataFrame,
    *,
    horizon: int = 5,
    seq_len: int = 32,
    epochs: int = 30,
    batch_size: int = 64,
    lr: float = 1e-3,
    test_ratio: float = 0.2,
) -> tuple[Any, dict[str, float]]:
    torch, nn = _torch()
    from torch.utils.data import DataLoader, TensorDataset

    Xdf = feature_matrix(ohlc)
    y_series = build_labels_forward_return(ohlc["close"].astype(float), horizon=horizon)
    valid = y_series.notna()
    Xdf = Xdf.loc[valid].reset_index(drop=True)
    y_series = y_series.loc[valid].reset_index(drop=True)

    X = Xdf.values.astype(np.float32)
    y = y_series.values.astype(np.float32)

    if len(X) < seq_len + 20:
        raise ValueError("Không đủ nến cho LSTM (cần seq_len + buffer).")

    X_seq, y_seq = _sequences(X, y, seq_len)
    n = len(X_seq)
    split = int(n * (1.0 - test_ratio))

    X_train, X_test = X_seq[:split], X_seq[split:]
    y_train, y_test = y_seq[:split], y_seq[split:]

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    n_feat = X_train.shape[2]

    class LSTMClf(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.lstm = nn.LSTM(n_feat, 32, 1, batch_first=True)
            self.fc = nn.Linear(32, 1)

        def forward(self, x: Any) -> Any:
            o, _ = self.lstm(x)
            last = o[:, -1, :]
            return torch.sigmoid(self.fc(last)).squeeze(-1)

    model = LSTMClf().to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.BCELoss()

    train_ds = TensorDataset(torch.from_numpy(X_train), torch.from_numpy(y_train))
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)

    model.train()
    for _ in range(epochs):
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad()
            pred = model(xb)
            loss = loss_fn(pred, yb)
            loss.backward()
            opt.step()

    model.eval()
    with torch.no_grad():
        xt = torch.from_numpy(X_test).to(device)
        prob = model(xt).cpu().numpy()
        pred = (prob >= 0.5).astype(int)
        acc = float((pred == y_test).mean()) if len(y_test) else 0.0

    metrics = {"accuracy": acc, "n_train": float(len(y_train)), "n_test": float(len(y_test))}
    return model, metrics


def predict_lstm_proba(model: Any, ohlc_window: pd.DataFrame, seq_len: int = 32) -> float:
    torch, _ = _torch()
    X = feature_matrix(ohlc_window).values.astype(np.float32)
    if len(X) < seq_len:
        return 0.5
    x = X[-seq_len:][np.newaxis, ...]
    device = next(model.parameters()).device
    model.eval()
    with torch.no_grad():
        t = torch.from_numpy(x).to(device)
        return float(model(t).cpu().numpy()[0])


def save_lstm(model: Any, path: str | Path) -> None:
    torch, _ = _torch()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), path)


def load_lstm(path: str | Path, n_features: int = 5, hidden: int = 32) -> Any:
    torch, nn = _torch()

    class LSTMClf(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.lstm = nn.LSTM(n_features, hidden, 1, batch_first=True)
            self.fc = nn.Linear(hidden, 1)

        def forward(self, x: Any) -> Any:
            o, _ = self.lstm(x)
            last = o[:, -1, :]
            return torch.sigmoid(self.fc(last)).squeeze(-1)

    m = LSTMClf()
    kwargs = {}
    try:
        kwargs["weights_only"] = True
        m.load_state_dict(torch.load(path, map_location="cpu", **kwargs))
    except TypeError:
        m.load_state_dict(torch.load(path, map_location="cpu"))
    m.eval()
    return m
