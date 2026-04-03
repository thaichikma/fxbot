"""Tests for NewsFilter (Finnhub parsing, no live HTTP in default tests)."""

from datetime import datetime, timezone

import pytest

from src.strategy.news_filter import NewsFilter, symbols_for_country


def test_symbols_for_country_us():
    assert "XAUUSD" in symbols_for_country("US")


@pytest.fixture
def nf():
    return NewsFilter(
        {
            "cache_ttl_minutes": 60,
            "block_before_high_minutes": 15,
            "block_after_high_minutes": 15,
            "block_before_critical_minutes": 30,
            "block_after_critical_minutes": 30,
            "critical_keywords": ["NFP"],
            "impact_levels_block": ["high"],
        }
    )


def test_is_news_blocked_high_impact_us(nf: NewsFilter):
    nf._cached_events = [
        {
            "event": "Non-Farm Payrolls",
            "country": "US",
            "impact": "high",
            "time": "2026-04-03T14:30:00+00:00",
        }
    ]
    t = datetime(2026, 4, 3, 14, 35, tzinfo=timezone.utc)
    blocked, reason = nf.is_news_blocked(t, "EURUSD")
    assert blocked is True
    assert "Non-Farm" in reason or "NFP" in reason or "News" in reason


def test_is_news_blocked_outside_window(nf: NewsFilter):
    nf._cached_events = [
        {
            "event": "GDP",
            "country": "US",
            "impact": "high",
            "time": "2026-04-03T14:30:00+00:00",
        }
    ]
    t = datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc)
    blocked, _ = nf.is_news_blocked(t, "EURUSD")
    assert blocked is False


def test_wrong_symbol_not_blocked(nf: NewsFilter):
    nf._cached_events = [
        {
            "event": "Tokyo CPI",
            "country": "JP",
            "impact": "high",
            "time": "2026-04-03T08:00:00+00:00",
        }
    ]
    t = datetime(2026, 4, 3, 8, 5, tzinfo=timezone.utc)
    blocked, _ = nf.is_news_blocked(t, "EURUSD")
    assert blocked is False


def test_usd_jpy_blocked_by_jp_event(nf: NewsFilter):
    nf._cached_events = [
        {
            "event": "BOJ Statement",
            "country": "JP",
            "impact": "high",
            "time": "2026-04-03T09:00:00+00:00",
        }
    ]
    t = datetime(2026, 4, 3, 9, 2, tzinfo=timezone.utc)
    blocked, _ = nf.is_news_blocked(t, "USDJPY")
    assert blocked is True
