"""
Paper trading validation — checklist before live / challenge (reference only).
"""


def paper_trading_checklist() -> list[str]:
    """Return ordered checklist strings."""
    return [
        "FTMO Free Trial or demo: Guardian daily PnL vs MetriX within 1–2%",
        "Kill switch: /kill closes all positions on MT5",
        "Session: no auto-trades outside London/NY/overlap when auto_mode on",
        "News: high-impact window blocks match broker time (Finnhub TZ)",
        "Spread: compare max_spread_points vs live average spreads",
        "Min 2 weeks paper trading before paid challenge",
        "Execution: slippage on live vs backtest assumptions",
    ]


def paper_trading_summary() -> str:
    return "Paper validation:\n- " + "\n- ".join(paper_trading_checklist())
