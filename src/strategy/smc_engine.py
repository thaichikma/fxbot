"""
SMC-style signal engine using pandas (no smartmoneyconcepts / numba).

Detects H4 bias, H1 last swing context, and M15 fair value gaps (3-candle),
then builds `Signal` objects with TP ladder from config.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
from loguru import logger

from src.data.models import Direction, MarketBias, Signal, SignalStatus, SignalType, StructureType
from src.utils.calculations import calculate_sl_distance_pips, calculate_tp_price


def _normalize_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or len(df) < 5:
        return pd.DataFrame()
    out = df.copy()
    cols = {c.lower(): c for c in out.columns}
    rename = {}
    for need in ("open", "high", "low", "close"):
        for k, v in cols.items():
            if k == need:
                rename[v] = need
                break
    out = out.rename(columns=rename)
    for c in ("open", "high", "low", "close"):
        if c not in out.columns:
            logger.warning("OHLC missing column: {}", c)
            return pd.DataFrame()
    if "time" not in out.columns and out.index.name != "time":
        out = out.reset_index(drop=True)
    return out


def _h4_bias(h4: pd.DataFrame) -> MarketBias:
    if len(h4) < 10:
        return MarketBias.NEUTRAL
    mid = len(h4) // 2
    a = h4["close"].iloc[:mid].mean()
    b = h4["close"].iloc[mid:].mean()
    if b > a * 1.0005:
        return MarketBias.BULLISH
    if b < a * 0.9995:
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


def _find_fvg_setup(
    m15: pd.DataFrame,
    bias: MarketBias,
    pip_size: float,
    fvg_min_pips: float,
) -> tuple[str, int] | None:
    """
    Returns (direction 'BUY'|'SELL', bar_index of FVG) for last qualifying gap.
    """
    if len(m15) < 5:
        return None
    for i in range(len(m15) - 1, 3, -1):
        high_i2 = float(m15["high"].iloc[i - 2])
        low_i = float(m15["low"].iloc[i])
        high_i = float(m15["high"].iloc[i])
        low_i2 = float(m15["low"].iloc[i - 2])

        # Bullish FVG: gap up — low[i] > high[i-2]
        if low_i > high_i2:
            gap_pips = (low_i - high_i2) / pip_size
            if gap_pips >= fvg_min_pips and bias in (MarketBias.BULLISH, MarketBias.NEUTRAL):
                return "BUY", i
        # Bearish FVG: high[i] < low[i-2]
        if high_i < low_i2:
            gap_pips = (low_i2 - high_i) / pip_size
            if gap_pips >= fvg_min_pips and bias in (MarketBias.BEARISH, MarketBias.NEUTRAL):
                return "SELL", i
    return None


class SMCEngine:
    """Rule-based SMC-style signals from multi-timeframe OHLCV."""

    def __init__(self, strategy_cfg: dict[str, Any], symbol_specs: dict[str, dict[str, Any]]):
        self._strategy = strategy_cfg
        self._symbols = symbol_specs

    def _pip_size(self, symbol: str) -> float:
        spec = self._symbols.get(symbol.upper(), {})
        return float(spec.get("pip_size", 0.0001))

    def analyze(self, symbol: str, data: dict[str, pd.DataFrame]) -> list[Signal]:
        def _get_frame(keys: tuple[str, ...]) -> pd.DataFrame:
            for k in keys:
                raw = data.get(k)
                if raw is not None:
                    return raw
            return pd.DataFrame()

        h4 = _normalize_ohlc(_get_frame(("H4", "h4")))
        h1 = _normalize_ohlc(_get_frame(("H1", "h1")))
        m15 = _normalize_ohlc(_get_frame(("M15", "m15")))
        if h4.empty or h1.empty or m15.empty:
            return []

        pip_size = self._pip_size(symbol)
        fvg_min = float(self._strategy.get("fvg_min_size_pips", 5))
        sl_buffer = float(self._strategy.get("sl_buffer_pips", 5))
        tp_ratios = list(self._strategy.get("tp_ratios") or [1.5, 2.0, 3.0])
        expiry_min = int(self._strategy.get("signal_expiry_minutes", 60))
        max_sig = int(self._strategy.get("max_signals_per_scan_per_symbol", 2))

        bias = _h4_bias(h4)
        struct = _h1_structure_label(h1)
        raw = _find_fvg_setup(m15, bias, pip_size, fvg_min)
        if raw is None:
            return []
        direction_s, idx = raw
        direction = Direction.BUY if direction_s == "BUY" else Direction.SELL

        entry = float(m15["close"].iloc[-1])
        row = m15.iloc[idx]
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
            signal_type=SignalType.FVG_FILL,
            entry_price=entry,
            stop_loss=sl_price,
            take_profit_1=tp1,
            take_profit_2=tp2,
            take_profit_3=tp3,
            h4_bias=bias,
            h1_structure=struct,
            session="",
            sl_distance_pips=sl_dist,
            risk_reward_ratio=rr1,
            timeframe="M15",
            confidence=min(100.0, 50.0 + min(sl_dist, 50.0)),
            created_at=datetime.now(timezone.utc),
            expiry=datetime.now(timezone.utc) + timedelta(minutes=expiry_min),
            status=SignalStatus.PENDING,
        )
        return [sig][:max_sig]
