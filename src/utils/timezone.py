"""
Timezone utilities for session management.

Key timezone conversions:
- FTMO daily reset: CE(S)T (Europe/Prague)
- Sessions: defined in UTC
- User display: Vietnam (UTC+7)
"""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

# Key timezones
UTC = ZoneInfo("UTC")
CEST = ZoneInfo("Europe/Prague")        # FTMO daily reset
VIETNAM = ZoneInfo("Asia/Ho_Chi_Minh")  # User display


def utc_now() -> datetime:
    """Current UTC time (timezone-aware)."""
    return datetime.now(UTC)


def cest_now() -> datetime:
    """Current CE(S)T time — used for FTMO daily reset."""
    return datetime.now(CEST)


def vietnam_now() -> datetime:
    """Current Vietnam time — for user-facing display."""
    return datetime.now(VIETNAM)


def to_utc(dt: datetime) -> datetime:
    """Convert any timezone-aware datetime to UTC."""
    return dt.astimezone(UTC)


def utc_today_start() -> datetime:
    """Midnight UTC today."""
    now = utc_now()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def cest_today_start() -> datetime:
    """Midnight CE(S)T today — FTMO's daily reset boundary."""
    now = cest_now()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def parse_utc_time(time_str: str) -> time:
    """Parse 'HH:MM' string to time object."""
    parts = time_str.split(":")
    return time(int(parts[0]), int(parts[1]))


def is_time_in_range(current: time, start: time, end: time) -> bool:
    """
    Check if current time is within [start, end] range.
    Handles overnight ranges (e.g., 23:00 - 07:00).
    """
    if start <= end:
        return start <= current <= end
    else:
        # Overnight range
        return current >= start or current <= end


def format_duration(seconds: float) -> str:
    """Format seconds into human-readable duration."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.0f}m"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours}h {mins}m"


def format_datetime_vn(dt: datetime) -> str:
    """Format datetime for Vietnam timezone display."""
    vn_dt = dt.astimezone(VIETNAM)
    return vn_dt.strftime("%d/%m %H:%M")
