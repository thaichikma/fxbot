"""
Risk manager — lot sizing and simple correlation guard (USD basket).
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from src.data.models import Signal
from src.utils.calculations import calculate_lot_size


def _pair_config(settings: dict, symbol: str) -> dict[str, Any]:
    for p in settings.get("pairs", []):
        if p.get("symbol") == symbol:
            return p
    return {}


def _usd_correlation_symbols(settings: dict) -> list[str]:
    """Symbols listed under correlation_groups.usd_pairs in symbols.yaml."""
    groups = settings.get("correlation_groups") or {}
    up = groups.get("usd_pairs")
    if isinstance(up, list):
        return [x for x in up if isinstance(x, str)]
    return []


class RiskManager:
    """Position sizing and exposure checks."""

    def __init__(
        self,
        settings: dict,
        symbols_specs: dict[str, dict[str, Any]],
        symbols_yaml: dict | None = None,
    ):
        self._risk = settings.get("risk", {})
        self._symbols = symbols_specs
        if symbols_yaml and symbols_yaml.get("correlation_groups"):
            self._settings = {**settings, "correlation_groups": symbols_yaml["correlation_groups"]}
        else:
            self._settings = settings

    def calculate_lot_size(self, symbol: str, sl_distance_pips: float, balance: float) -> float:
        spec = self._symbols.get(symbol.upper(), {})
        pip_value = float(spec.get("pip_value_per_lot", 10.0))
        pair = _pair_config(self._settings, symbol)
        min_vol = float(pair.get("min_volume", spec.get("min_volume", 0.01)))
        step = float(pair.get("volume_step", spec.get("volume_step", 0.01)))
        max_lot = float(self._risk.get("max_lot_size", 1.0))
        risk_pct = float(self._risk.get("risk_per_trade", 0.01))

        lot = calculate_lot_size(
            balance=balance,
            risk_pct=risk_pct,
            sl_distance_pips=sl_distance_pips,
            pip_value_per_lot=pip_value,
            min_volume=min_vol,
            volume_step=step,
            max_lot=max_lot,
        )
        logger.debug("Risk lot | {} | SL={:.1f} pips | lot={:.4f}", symbol, sl_distance_pips, lot)
        return lot

    def calculate_lot_size_with_risk_override(
        self,
        symbol: str,
        sl_distance_pips: float,
        balance: float,
        risk_pct: float,
    ) -> float:
        spec = self._symbols.get(symbol.upper(), {})
        pip_value = float(spec.get("pip_value_per_lot", 10.0))
        pair = _pair_config(self._settings, symbol)
        min_vol = float(pair.get("min_volume", spec.get("min_volume", 0.01)))
        step = float(pair.get("volume_step", spec.get("volume_step", 0.01)))
        max_lot = float(self._risk.get("max_lot_size", 1.0))
        return calculate_lot_size(
            balance=balance,
            risk_pct=risk_pct,
            sl_distance_pips=sl_distance_pips,
            pip_value_per_lot=pip_value,
            min_volume=min_vol,
            volume_step=step,
            max_lot=max_lot,
        )

    def check_correlation(self, signal: Signal, open_positions: list[dict]) -> tuple[bool, str]:
        """
        Limit same-direction exposure in USD correlation group (EURUSD, GBPUSD, XAUUSD, ...).
        """
        max_corr = int(self._risk.get("max_correlation_trades", 2))
        group = _usd_correlation_symbols(self._settings)
        if not group or signal.symbol not in group:
            return True, ""

        sig_dir = signal.direction.value
        same = 0
        for pos in open_positions:
            if pos.get("symbol") not in group:
                continue
            if pos.get("type") == sig_dir:
                same += 1
        if same >= max_corr:
            return False, f"Correlation cap: {same}/{max_corr} same-direction in USD group"
        return True, ""
