"""
Multi-pair signal scanner — MT5 rates → SMCEngine → session & news filters.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from loguru import logger

from src.data.db import Database
from src.data.models import Signal
from src.strategy.news_filter import NewsFilter
from src.strategy.session_filter import SessionFilter
from src.strategy.smc_engine import SMCEngine


def _signal_to_db_dict(sig: Signal) -> dict[str, Any]:
    return {
        "id": sig.id,
        "symbol": sig.symbol,
        "direction": sig.direction.value,
        "signal_type": sig.signal_type.value,
        "entry_price": sig.entry_price,
        "stop_loss": sig.stop_loss,
        "take_profit_1": sig.take_profit_1,
        "take_profit_2": sig.take_profit_2,
        "take_profit_3": sig.take_profit_3,
        "h4_bias": sig.h4_bias.value,
        "h1_structure": sig.h1_structure.value,
        "session": sig.session,
        "sl_distance_pips": sig.sl_distance_pips,
        "risk_reward_ratio": sig.risk_reward_ratio,
        "timeframe": sig.timeframe,
        "confidence": sig.confidence,
        "created_at": sig.created_at.isoformat(),
        "expiry": sig.expiry.isoformat() if sig.expiry else "",
        "status": sig.status.value,
    }


class SignalScanner:
    """Scan configured pairs and return actionable signals (Phase 2: notify only)."""

    def __init__(
        self,
        settings: dict[str, Any],
        symbol_specs: dict[str, Any],
        session_filter: SessionFilter,
        news_filter: NewsFilter,
        smc_engine: SMCEngine,
    ):
        self._settings = settings
        self._symbol_specs = symbol_specs
        self._session = session_filter
        self._news = news_filter
        self._engine = smc_engine

    def _price_epsilon(self, symbol: str) -> float:
        spec = self._symbol_specs.get(symbol.upper(), {})
        pip = float(spec.get("pip_size", 0.0001))
        return max(pip * 5.0, 1e-8)

    async def scan(
        self,
        mt5_client: Any,
        db: Database | None = None,
        now: datetime | None = None,
    ) -> list[Signal]:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        system = self._settings.get("system", {})
        if not system.get("signal_scan_enabled", True):
            return []

        await self._news.refresh(now)
        dedupe_min = int(system.get("signal_dedupe_minutes", 30))

        results: list[Signal] = []

        for pair in self._settings.get("pairs", []):
            if not pair.get("enabled", True):
                continue
            symbol = pair["symbol"]
            tf = pair.get("timeframes", {})
            bias_tf = tf.get("bias", "H4")
            structure_tf = tf.get("structure", "H1")
            entry_tf = tf.get("entry", "M15")

            h4 = mt5_client.get_rates(symbol, bias_tf, 200)
            h1 = mt5_client.get_rates(symbol, structure_tf, 500)
            m15 = mt5_client.get_rates(symbol, entry_tf, 500)
            if h4 is None or h1 is None or m15 is None:
                logger.debug("No rates for {} — skip", symbol)
                continue
            if getattr(h4, "empty", False) or getattr(h1, "empty", False) or getattr(m15, "empty", False):
                continue

            data = {"H4": h4, "H1": h1, "M15": m15}
            signals = self._engine.analyze(symbol, data)

            for sig in signals:
                active, sess_name = self._session.is_trading_session(now)
                if not active:
                    continue
                sig.session = sess_name

                blocked, reason = self._news.is_news_blocked(now, symbol)
                if blocked:
                    logger.info("Signal skipped (news) {} | {}", symbol, reason)
                    continue

                eps = self._price_epsilon(symbol)
                if db:
                    dup = await db.has_similar_signal_recent(
                        symbol,
                        sig.direction.value,
                        sig.entry_price,
                        minutes=dedupe_min,
                        price_epsilon=eps,
                    )
                    if dup:
                        logger.debug("Dedupe skip | {}", symbol)
                        continue
                    await db.insert_signal(_signal_to_db_dict(sig))

                results.append(sig)

        return results
