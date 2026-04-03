"""
Session filter — London / New York / Asian windows (UTC) from settings.yaml.

Overlap (London ∩ New York) is treated as prime session for quality scoring.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Any


def _parse_hhmm(s: str) -> time:
    h, m = s.strip().split(":")
    return time(int(h), int(m), tzinfo=timezone.utc)


def _to_minutes_utc(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    t = dt.astimezone(timezone.utc).timetz()
    return t.hour * 60 + t.minute


def _minutes_in_range(
    minutes: int,
    start: time,
    end: time,
    *,
    wrap_midnight: bool = False,
) -> bool:
    """Inclusive range in [start,end); wrap_midnight for asian 23:00–07:00."""
    sm = start.hour * 60 + start.minute
    em = end.hour * 60 + end.minute
    if wrap_midnight:
        if sm >= em:
            return minutes >= sm or minutes < em
        return sm <= minutes < em
    return sm <= minutes < em


@dataclass
class SessionConfig:
    london: dict[str, Any]
    new_york: dict[str, Any]
    asian: dict[str, Any]


class SessionFilter:
    """Trading session detection from config sessions block."""

    def __init__(self, sessions_cfg: dict[str, Any]):
        self._london = sessions_cfg.get("london", {})
        self._ny = sessions_cfg.get("new_york", {})
        self._asian = sessions_cfg.get("asian", {})
        self._london_start = _parse_hhmm(self._london.get("start", "07:00"))
        self._london_end = _parse_hhmm(self._london.get("end", "16:00"))
        self._ny_start = _parse_hhmm(self._ny.get("start", "12:30"))
        self._ny_end = _parse_hhmm(self._ny.get("end", "21:00"))
        self._asian_start = _parse_hhmm(self._asian.get("start", "23:00"))
        self._asian_end = _parse_hhmm(self._asian.get("end", "07:00"))

    def classify_session(self, now: datetime) -> str:
        """Return overlap | london | new_york | asian | off_session."""
        m = _to_minutes_utc(now)
        in_london = _minutes_in_range(m, self._london_start, self._london_end)
        in_ny = _minutes_in_range(m, self._ny_start, self._ny_end)
        in_asian = _minutes_in_range(
            m, self._asian_start, self._asian_end, wrap_midnight=True
        )

        if in_london and in_ny:
            return "overlap"
        if in_london:
            return "london"
        if in_ny:
            return "new_york"
        if in_asian:
            return "asian"
        return "off_session"

    def is_trading_session(self, now: datetime) -> tuple[bool, str]:
        """
        True if within london, new_york, overlap, or asian (signal-only window).
        Second value is session name or off_session.
        """
        name = self.classify_session(now)
        active = name != "off_session"
        return active, name

    def auto_trade_allowed(self, now: datetime) -> bool:
        """True when auto execution is allowed (London/NY/overlap, not Asian-only)."""
        name = self.classify_session(now)
        if name == "overlap":
            return bool(self._london.get("auto_trade", True)) and bool(
                self._ny.get("auto_trade", True)
            )
        if name == "london":
            return bool(self._london.get("auto_trade", True))
        if name == "new_york":
            return bool(self._ny.get("auto_trade", True))
        if name == "asian":
            return bool(self._asian.get("auto_trade", False))
        return False

    def session_quality(self, now: datetime) -> float:
        """0–1 score for current session quality."""
        name = self.classify_session(now)
        if name == "overlap":
            return 1.0
        if name in ("london", "new_york"):
            return 0.8
        if name == "asian":
            return 0.3
        return 0.0
