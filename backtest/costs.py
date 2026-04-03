"""
Approximate transaction costs for backtest (spread, commission, overnight swap).

Not tick-level and not identical to FTMO/broker execution — see settings comments.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.utils.calculations import calculate_lot_size, calculate_sl_distance_pips


def _cfg_bool(val: Any, default: bool = False) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    s = str(val).strip().lower()
    if s in ("0", "false", "no", "off", ""):
        return False
    if s in ("1", "true", "yes", "on"):
        return True
    return default


def costs_feature_enabled(settings: dict[str, Any]) -> bool:
    """Whether backtest.costs.enabled is true."""
    cfg = settings.get("backtest", {}).get("costs", {})
    return _cfg_bool(cfg.get("enabled"), False)


def _pair_cfg(settings: dict, symbol: str) -> dict[str, Any]:
    for p in settings.get("pairs", []) or []:
        if p.get("symbol") == symbol:
            return p
    return {}


def spread_pips_from_mode(spec: dict, pair: dict, mode: str) -> float:
    """Effective spread in pips (not points)."""
    pip_size = float(spec.get("pip_size", 0.0001))
    point_size = float(spec.get("point_size", pip_size * 0.1))
    if mode == "none" or pip_size <= 0:
        return 0.0
    if mode == "max_pair":
        pts = float(pair.get("max_spread_points") or spec.get("typical_spread_points", 0))
    else:
        pts = float(spec.get("typical_spread_points", 0))
    return pts * point_size / pip_size


def rollover_nights_utc(entry: datetime, exit: datetime) -> int:
    """UTC calendar days between entry and exit dates (0 if same day)."""
    if entry.tzinfo is None:
        entry = entry.replace(tzinfo=timezone.utc)
    if exit.tzinfo is None:
        exit = exit.replace(tzinfo=timezone.utc)
    entry = entry.astimezone(timezone.utc)
    exit = exit.astimezone(timezone.utc)
    if exit.date() <= entry.date():
        return 0
    return (exit.date() - entry.date()).days


def trade_transaction_costs_usd(
    *,
    settings: dict[str, Any],
    symbol: str,
    direction: str,
    entry_time: datetime,
    exit_time: datetime,
    equity_at_entry: float,
    entry_price: float,
    sl_price: float,
    spec: dict[str, Any],
    costs_cfg: dict[str, Any],
) -> tuple[float, dict[str, float]]:
    """
    Returns (total_cost_usd, breakdown).

    Breakdown keys: spread, commission, swap
    """
    spread_mode = str(costs_cfg.get("spread_mode", "typical")).lower()
    comm_rt = float(costs_cfg.get("commission_usd_per_lot_round_turn", 0.0))
    swap_long = float(costs_cfg.get("swap_long_usd_per_lot_per_night", 0.0))
    swap_short = float(costs_cfg.get("swap_short_usd_per_lot_per_night", 0.0))

    pair = _pair_cfg(settings, symbol)
    pip_size = float(spec.get("pip_size", 0.0001))
    pip_value = float(spec.get("pip_value_per_lot", 10.0))
    min_vol = float(pair.get("min_volume", spec.get("min_volume", 0.01)))
    step = float(pair.get("volume_step", spec.get("volume_step", 0.01)))
    max_lot = float(settings.get("risk", {}).get("max_lot_size", 1.0))
    risk_pct = float(settings.get("risk", {}).get("risk_per_trade", 0.01))

    sl_pips = calculate_sl_distance_pips(entry_price, sl_price, pip_size)
    if sl_pips <= 0:
        return 0.0, {"spread": 0.0, "commission": 0.0, "swap": 0.0}

    lot = calculate_lot_size(
        balance=equity_at_entry,
        risk_pct=risk_pct,
        sl_distance_pips=sl_pips,
        pip_value_per_lot=pip_value,
        min_volume=min_vol,
        volume_step=step,
        max_lot=max_lot,
    )

    sp = spread_pips_from_mode(spec, pair, spread_mode)
    spread_usd = sp * pip_value * lot

    commission_usd = comm_rt * lot

    nights = rollover_nights_utc(entry_time, exit_time)
    swap_rate = swap_long if direction == "BUY" else swap_short
    swap_usd = swap_rate * lot * float(nights)

    total = spread_usd + commission_usd + swap_usd
    return total, {
        "spread": spread_usd,
        "commission": commission_usd,
        "swap": swap_usd,
    }
