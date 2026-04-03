"""
Tín hiệu từ mô hình ML (XGBoost) — xác suất giá tăng sau horizon nến.

Cần train trước (`scripts/ml_train.py`) và đặt `ml.model_path` trong settings.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from src.data.models import Direction, MarketBias, Signal, SignalStatus, SignalType, StructureType
from src.utils.calculations import calculate_sl_distance_pips, calculate_tp_price


class MLEngine:
    """Load XGBoost pickle; phân tích khung entry (M15/M5) trong `data`."""

    def __init__(self, settings: dict[str, Any], symbol_specs: dict[str, dict[str, Any]]):
        self._strategy = dict(settings.get("strategy", {}))
        self._symbols = symbol_specs
        self._ml = dict(settings.get("ml", {}))
        self._model: Any = None
        path = str(self._ml.get("model_path", "") or "").strip()
        if path and self._ml.get("enabled", False):
            p = Path(path)
            if p.is_file():
                try:
                    from src.ml.models_xgb import load_xgb

                    self._model = load_xgb(p)
                    logger.info("ML model loaded | {}", p)
                except Exception as e:
                    logger.warning("ML load failed: {}", e)

    def _pip_size(self, symbol: str) -> float:
        spec = self._symbols.get(symbol.upper(), {})
        return float(spec.get("pip_size", 0.0001))

    def analyze(self, symbol: str, data: dict[str, pd.DataFrame]) -> list[Signal]:
        if self._model is None:
            return []

        entry_tf = str(self._ml.get("entry_timeframe_key", "M15"))
        df = data.get(entry_tf)
        if df is None:
            df = data.get(entry_tf.lower())
        if df is None:
            df = data.get("M15")
        if df is None or len(df) < 40:
            return []

        min_rows = int(self._ml.get("min_ohlc_rows", 60))
        if len(df) < min_rows:
            return []

        try:
            from src.ml.models_xgb import predict_proba_up
        except Exception:
            return []

        prob = predict_proba_up(self._model, df)
        thr = float(self._ml.get("prob_threshold", 0.55))
        if prob >= thr:
            direction_s = "BUY"
        elif prob <= (1.0 - thr):
            direction_s = "SELL"
        else:
            return []
        direction = Direction.BUY if direction_s == "BUY" else Direction.SELL

        pip_size = self._pip_size(symbol)
        sl_buffer = float(self._strategy.get("sl_buffer_pips", 5))
        tp_ratios = list(self._strategy.get("tp_ratios") or [1.5, 2.0, 3.0])
        expiry_min = int(self._strategy.get("signal_expiry_minutes", 60))

        entry = float(df["close"].iloc[-1])
        atr_mult = float(self._ml.get("sl_atr_mult", 2.0))
        # proxy SL distance from recent range
        recent = df.tail(20)
        rng = float((recent["high"].max() - recent["low"].min()) / pip_size)
        sl_pips = max(sl_buffer, rng * 0.2 * atr_mult)
        if direction == Direction.BUY:
            sl_price = entry - pip_size * sl_pips
        else:
            sl_price = entry + pip_size * sl_pips

        sl_dist = calculate_sl_distance_pips(entry, sl_price, pip_size)
        rr1 = float(tp_ratios[0]) if tp_ratios else 1.5
        tp1 = calculate_tp_price(entry, sl_price, rr1, direction_s)
        tp2 = calculate_tp_price(entry, sl_price, float(tp_ratios[1]), direction_s) if len(tp_ratios) > 1 else tp1
        tp3 = calculate_tp_price(entry, sl_price, float(tp_ratios[2]), direction_s) if len(tp_ratios) > 2 else tp2

        sig = Signal(
            id=str(uuid.uuid4()),
            symbol=symbol,
            direction=direction,
            signal_type=SignalType.ML_PREDICTION,
            entry_price=entry,
            stop_loss=sl_price,
            take_profit_1=tp1,
            take_profit_2=tp2,
            take_profit_3=tp3,
            h4_bias=MarketBias.NEUTRAL,
            h1_structure=StructureType.NONE,
            session="",
            sl_distance_pips=sl_dist,
            risk_reward_ratio=rr1,
            timeframe=entry_tf,
            confidence=min(99.0, 40.0 + abs(prob - 0.5) * 120.0),
            created_at=datetime.now(timezone.utc),
            expiry=datetime.now(timezone.utc) + timedelta(minutes=expiry_min),
            status=SignalStatus.PENDING,
        )
        return [sig]
