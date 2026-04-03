"""
News filter — Finnhub economic calendar with in-memory cache.

`refresh()` must be awaited periodically; `is_news_blocked` is sync and uses cache only.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from loguru import logger

FINNHUB_ECONOMIC_URL = "https://finnhub.io/api/v1/calendar/economic"

# Map calendar country codes to symbols that should respect that release
COUNTRY_TO_SYMBOLS: dict[str, list[str]] = {
    "US": ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"],
    "USA": ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"],
    "EU": ["EURUSD", "GBPUSD"],
    "EZ": ["EURUSD", "GBPUSD"],
    "GB": ["GBPUSD", "EURUSD"],
    "UK": ["GBPUSD", "EURUSD"],
    "JP": ["USDJPY"],
    "JPn": ["USDJPY"],
    "CH": ["EURUSD", "USDJPY"],
    "AU": ["EURUSD", "GBPUSD", "XAUUSD"],
    "CA": ["USDCAD", "EURUSD", "XAUUSD"],
    "NZ": ["NZDUSD", "EURUSD"],
    "CN": ["XAUUSD", "USDJPY"],
}


def _normalize_country(raw: str) -> str:
    return (raw or "").strip().upper()


def symbols_for_country(country: str) -> list[str]:
    key = _normalize_country(country)
    return COUNTRY_TO_SYMBOLS.get(key, COUNTRY_TO_SYMBOLS["US"])


def _parse_event_time(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    s = str(value).strip()
    if not s:
        return None
    # ISO or "YYYY-MM-DD HH:MM:SS"
    try:
        if "T" in s:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        else:
            dt = datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


class NewsFilter:
    """Finnhub-backed news blocking with TTL cache."""

    def __init__(self, news_cfg: dict[str, Any] | None = None):
        cfg = news_cfg or {}
        self._cache_ttl = timedelta(minutes=float(cfg.get("cache_ttl_minutes", 45)))
        self._before_high = timedelta(minutes=float(cfg.get("block_before_high_minutes", 15)))
        self._after_high = timedelta(minutes=float(cfg.get("block_after_high_minutes", 15)))
        self._before_crit = timedelta(minutes=float(cfg.get("block_before_critical_minutes", 30)))
        self._after_crit = timedelta(minutes=float(cfg.get("block_after_critical_minutes", 30)))
        raw_kw = cfg.get("critical_keywords") or []
        self._critical_keywords = [k.upper() for k in raw_kw]
        impacts = cfg.get("impact_levels_block") or ["high"]
        self._impact_block = {str(x).lower() for x in impacts}
        # Set false if Finnhub key has no calendar access (403) or you want news off without removing the key.
        self._calendar_enabled = bool(cfg.get("calendar_enabled", True))

        self._token = os.getenv("FINNHUB_API_KEY", "")
        self._cached_events: list[dict[str, Any]] = []
        self._cache_fetched_at: datetime | None = None
        self._last_error: str | None = None

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def _is_critical_event(self, event_name: str) -> bool:
        upper = event_name.upper()
        return any(k in upper for k in self._critical_keywords)

    def _should_block_impact(self, impact: str) -> bool:
        return str(impact).lower() in self._impact_block

    async def refresh(self, now: datetime | None = None) -> None:
        """Fetch calendar if cache expired or empty."""
        now = now or datetime.now(timezone.utc)
        if self._cache_fetched_at and (now - self._cache_fetched_at) < self._cache_ttl:
            return
        if not self._calendar_enabled:
            self._cached_events = []
            self._cache_fetched_at = now
            self._last_error = None
            return
        if not self._token:
            logger.warning("FINNHUB_API_KEY not set — news filter inactive")
            self._cached_events = []
            self._cache_fetched_at = now
            return

        day = now.date()
        from_d = (day - timedelta(days=1)).isoformat()
        to_d = (day + timedelta(days=1)).isoformat()
        params = {"from": from_d, "to": to_d, "token": self._token}

        try:
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(FINNHUB_ECONOMIC_URL, params=params) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        self._last_error = f"HTTP {resp.status}: {text[:200]}"
                        self._cached_events = []
                        self._cache_fetched_at = now
                        if resp.status in (401, 403):
                            logger.warning(
                                "Finnhub economic calendar: access denied (HTTP {}). "
                                "Free API keys often exclude this endpoint — "
                                "news blocking is off. Fix: paid Finnhub tier, or set "
                                "news.calendar_enabled: false in settings.yaml, or remove FINNHUB_API_KEY.",
                                resp.status,
                            )
                        else:
                            logger.error("Finnhub calendar error: {}", self._last_error)
                        return
                    data = await resp.json()
        except Exception as e:
            self._last_error = str(e)
            self._cached_events = []
            self._cache_fetched_at = now
            logger.error("Finnhub fetch failed: {}", e)
            return

        self._last_error = None
        # Finnhub returns { "economicCalendar": [ {...}, ... ] }
        events = data.get("economicCalendar") or data.get("economic") or []
        if isinstance(events, dict):
            events = list(events.values())
        self._cached_events = events if isinstance(events, list) else []
        self._cache_fetched_at = now
        logger.debug("Finnhub calendar loaded | {} events", len(self._cached_events))

    def is_news_blocked(self, now: datetime, symbol: str) -> tuple[bool, str]:
        """
        Returns (blocked, reason). Uses only cached events — call refresh() first in the loop.
        """
        if not self._cached_events:
            return False, ""

        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now = now.astimezone(timezone.utc)

        sym = symbol.upper()
        for ev in self._cached_events:
            impact = str(ev.get("impact") or ev.get("importance") or "").lower()
            event_name = str(ev.get("event") or ev.get("title") or "")
            if impact:
                if not self._should_block_impact(impact):
                    continue
            elif not self._is_critical_event(event_name):
                continue

            country = str(ev.get("country") or ev.get("region") or "US")
            affected = symbols_for_country(country)
            if sym not in affected:
                continue

            event_time = _parse_event_time(
                ev.get("time") or ev.get("date") or ev.get("releaseTime")
            )
            if event_time is None:
                continue

            critical = self._is_critical_event(event_name)
            before = self._before_crit if critical else self._before_high
            after = self._after_crit if critical else self._after_high
            window_start = event_time - before
            window_end = event_time + after

            if window_start <= now <= window_end:
                reason = f"News: {event_name[:80]} ({country}) @ {event_time.isoformat()}"
                return True, reason

        return False, ""
