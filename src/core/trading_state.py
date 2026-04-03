"""Mutable runtime flags (Telegram / hybrid mode)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TradingState:
    """Hybrid execution: scan always; orders only when execution_enabled + auto_mode + session."""

    auto_mode: bool = True
    execution_enabled: bool = False
    risk_per_trade: float | None = None  # if set, overrides settings risk.risk_per_trade

    @classmethod
    def from_settings(cls, system: dict) -> "TradingState":
        return cls(
            auto_mode=bool(system.get("auto_mode", True)),
            execution_enabled=bool(system.get("execution_enabled", False)),
            risk_per_trade=None,
        )

    def effective_risk_pct(self, default: float) -> float:
        return self.risk_per_trade if self.risk_per_trade is not None else default
