"""
Load OHLCV for backtests — CSV or resample from M15.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_ohlc_csv(path: str | Path) -> pd.DataFrame:
    """
    Load CSV with columns: time, open, high, low, close (volume optional).
    `time` parsed as UTC datetime.
    """
    p = Path(path)
    df = pd.read_csv(p)
    cols = {c.lower(): c for c in df.columns}
    tcol = cols.get("time") or cols.get("date") or cols.get("datetime")
    if tcol is None:
        raise ValueError("CSV must have time/date/datetime column")
    df["time"] = pd.to_datetime(df[tcol], utc=True)
    for c in ("open", "high", "low", "close"):
        if c not in {x.lower() for x in df.columns}:
            raise ValueError(f"Missing column: {c}")
        key = [x for x in df.columns if x.lower() == c][0]
        df[c] = df[key].astype(float)
    return df[["time", "open", "high", "low", "close"]].sort_values("time").reset_index(drop=True)


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample M15-style OHLC to H1/H4 etc. rule e.g. '1h', '4h'."""
    x = df.set_index("time")
    o = x["open"].resample(rule).first()
    h = x["high"].resample(rule).max()
    l = x["low"].resample(rule).min()
    c = x["close"].resample(rule).last()
    out = pd.DataFrame({"open": o, "high": h, "low": l, "close": c}).dropna()
    out = out.reset_index()
    if out.columns[0] != "time":
        out.rename(columns={out.columns[0]: "time"}, inplace=True)
    return out


def build_multi_timeframe(m15: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Build H1 and H4 from M15 (assumes ~15min bars)."""
    h1 = resample_ohlc(m15, "1h")
    h4 = resample_ohlc(m15, "4h")
    return {"M15": m15, "H1": h1, "H4": h4}
