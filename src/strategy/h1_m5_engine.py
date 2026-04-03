"""
Chiến lược đa khung: H1 xác định xu hướng (EMA), M5 vào lệnh (FVG cùng logic SMC trên M5).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
from loguru import logger

from src.data.models import Direction, MarketBias, Signal, SignalStatus, SignalType, StructureType
from src.strategy.smc_engine import _find_fvg_setup, _normalize_ohlc
from src.utils.calculations import calculate_sl_distance_pips, calculate_tp_price


def _h1_trend_ema(h1: pd.DataFrame) -> MarketBias:
    """Xu hướng H1: EMA nhanh vs EMA chậm trên close."""
    if len(h1) < 30:
        return MarketBias.NEUTRAL
    c = h1["close"].astype(float)
    ema_f = c.ewm(span=12, adjust=False).mean()
    ema_s = c.ewm(span=26, adjust=False).mean()
    if float(ema_f.iloc[-1]) > float(ema_s.iloc[-1]):
        return MarketBias.BULLISH
    if float(ema_f.iloc[-1]) < float(ema_s.iloc[-1]):
        return MarketBias.BEARISH
    return MarketBias.NEUTRAL


def _h1_structure_label(h1: pd.DataFrame) -> StructureType:
    if len(h1) < 20:
        return StructureType.NONE
    recent = h1["close"].iloc[-5:].mean()
    older = h1["close"].iloc[-20:-5].mean()
    if recent > older:
        return StructureType.BOS
    if recent < older:
        return StructureType.BOS
    return StructureType.NONE


class H1M5Engine:
    """H1 trend + M5 FVG entry — cùng tham số fvg/sl/tp như SMC."""

    def __init__(self, strategy_cfg: dict[str, Any], symbol_specs: dict[str, dict[str, Any]]):
        self._strategy = strategy_cfg
        self._symbols = symbol_specs

    def _pip_size(self, symbol: str) -> float:
        spec = self._symbols.get(symbol.upper(), {})
        return float(spec.get("pip_size", 0.0001))

    def analyze(self, symbol: str, data: dict[str, pd.DataFrame]) -> list[Signal]:
        def _get(keys: tuple[str, ...]) -> pd.DataFrame | None:
            for k in keys:
                raw = data.get(k)
                if raw is not None:
                    return raw
            return None

        h1 = _normalize_ohlc(_get(("H1", "h1")))
        m5 = _normalize_ohlc(_get(("M5", "m5")))
        if h1.empty or m5.empty:
            return []

        pip_size = self._pip_size(symbol)
        fvg_min = float(self._strategy.get("fvg_min_size_pips", 5))
        sl_buffer = float(self._strategy.get("sl_buffer_pips", 5))
        tp_ratios = list(self._strategy.get("tp_ratios") or [1.5, 2.0, 3.0])
        expiry_min = int(self._strategy.get("signal_expiry_minutes", 60))
        max_sig = int(self._strategy.get("max_signals_per_scan_per_symbol", 2))

        bias = _h1_trend_ema(h1)
        if bias == MarketBias.NEUTRAL:
            logger.debug("H1M5 skip {} — H1 neutral", symbol)
            return []

        struct = _h1_structure_label(h1)
        raw = _find_fvg_setup(m5, bias, pip_size, fvg_min)
        if raw is None:
            return []

        direction_s, idx = raw
        direction = Direction.BUY if direction_s == "BUY" else Direction.SELL

        entry = float(m5["close"].iloc[-1])
        row = m5.iloc[idx]
        if direction == Direction.BUY:
            sl_price = float(row["low"]) - pip_size * sl_buffer
            if sl_price >= entry:
                sl_price = entry - pip_size * max(fvg_min, sl_buffer)
        else:
            sl_price = float(row["high"]) + pip_size * sl_buffer
            if sl_price <= entry:
                sl_price = entry + pip_size * max(fvg_min, sl_buffer)

        sl_dist = calculate_sl_distance_pips(entry, sl_price, pip_size)
        rr1 = float(tp_ratios[0]) if tp_ratios else 1.5
        tp1 = calculate_tp_price(entry, sl_price, rr1, direction_s)
        tp2 = calculate_tp_price(entry, sl_price, float(tp_ratios[1]), direction_s) if len(tp_ratios) > 1 else tp1
        tp3 = calculate_tp_price(entry, sl_price, float(tp_ratios[2]), direction_s) if len(tp_ratios) > 2 else tp2

        sig = Signal(
            id=str(uuid.uuid4()),
            symbol=symbol,
            direction=direction,
            signal_type=SignalType.H1_M5_FVG,
            entry_price=entry,
            stop_loss=sl_price,
            take_profit_1=tp1,
            take_profit_2=tp2,
            take_profit_3=tp3,
            h4_bias=MarketBias.NEUTRAL,
            h1_structure=struct,
            session="",
            sl_distance_pips=sl_dist,
            risk_reward_ratio=rr1,
            timeframe="M5",
            confidence=min(100.0, 55.0 + min(sl_dist, 40.0)),
            created_at=datetime.now(timezone.utc),
            expiry=datetime.now(timezone.utc) + timedelta(minutes=expiry_min),
            status=SignalStatus.PENDING,
        )
        return [sig][:max_sig]
