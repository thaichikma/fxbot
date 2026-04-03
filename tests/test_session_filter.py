"""Tests for SessionFilter."""

from datetime import datetime, timezone

import pytest

from src.strategy.session_filter import SessionFilter


@pytest.fixture
def sessions_cfg():
    return {
        "london": {"start": "07:00", "end": "16:00", "auto_trade": True},
        "new_york": {"start": "12:30", "end": "21:00", "auto_trade": True},
        "asian": {"start": "23:00", "end": "07:00", "auto_trade": False},
    }


@pytest.fixture
def filt(sessions_cfg):
    return SessionFilter(sessions_cfg)


@pytest.mark.parametrize(
    "iso_utc,expected_name",
    [
        ("2026-04-03T12:45:00+00:00", "overlap"),  # in london and NY
        ("2026-04-03T08:00:00+00:00", "london"),
        ("2026-04-03T18:00:00+00:00", "new_york"),
        ("2026-04-03T03:00:00+00:00", "asian"),
        ("2026-04-03T22:00:00+00:00", "off_session"),  # gap 21:00 NY end – 23:00 asian
    ],
)
def test_classify_session(filt, iso_utc, expected_name):
    now = datetime.fromisoformat(iso_utc)
    assert filt.classify_session(now) == expected_name


def test_overlap_quality(filt):
    now = datetime(2026, 4, 3, 14, 0, tzinfo=timezone.utc)
    assert filt.session_quality(now) == 1.0


def test_london_quality(filt):
    now = datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc)
    assert filt.session_quality(now) == 0.8


def test_auto_trade_asian_off(filt):
    now = datetime(2026, 4, 3, 3, 0, tzinfo=timezone.utc)
    assert filt.auto_trade_allowed(now) is False


def test_auto_trade_overlap_on(filt):
    now = datetime(2026, 4, 3, 13, 0, tzinfo=timezone.utc)
    assert filt.auto_trade_allowed(now) is True


def test_is_trading_session_off(filt):
    now = datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc)
    ok, name = filt.is_trading_session(now)
    assert ok is True
    assert name == "london"
