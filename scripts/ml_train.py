#!/usr/bin/env python3
"""
Huấn luyện mô hình ML trên CSV OHLCV.

  PYTHONPATH=. python scripts/ml_train.py --csv data/backtest/sample_m15.csv --model xgb --out models/xgb.pkl
  PYTHONPATH=. python scripts/ml_train.py --csv data/backtest/sample_m15.csv --model lstm --out models/lstm.pt
"""

from __future__ import annotations

import argparse
from pathlib import Path

from backtest.data_loader import load_ohlc_csv


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--csv", required=True, help="CSV M5/M15 OHLC")
    p.add_argument("--model", choices=("xgb", "lstm"), default="xgb")
    p.add_argument("--out", required=True, help="File đầu ra (.pkl / .pt)")
    p.add_argument("--horizon", type=int, default=5)
    args = p.parse_args()

    ohlc = load_ohlc_csv(args.csv)
    out = Path(args.out)

    if args.model == "xgb":
        from src.ml.models_xgb import save_xgb, train_xgb_classifier

        model, metrics = train_xgb_classifier(ohlc, horizon=args.horizon)
        save_xgb(model, out)
        print("XGBoost | metrics:", metrics, "| saved:", out.resolve())
    else:
        from src.ml.models_lstm import save_lstm, train_lstm_classifier

        model, metrics = train_lstm_classifier(ohlc, horizon=args.horizon)
        save_lstm(model, out)
        print("LSTM | metrics:", metrics, "| saved:", out.resolve())


if __name__ == "__main__":
    main()
