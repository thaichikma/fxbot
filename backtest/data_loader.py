"""
Load OHLCV for backtests — CSV or resample from M15.

Hỗ trợ:
- CSV phẩy: `time,open,high,low,close` (chuẩn repo)
- Export MT4/MT5 kiểu `Date;Open;High;Low;Close;Volume` (XAU_*.csv)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def _read_csv_flexible(path: Path) -> pd.DataFrame:
    with open(path, encoding="utf-8", errors="replace") as f:
        first = f.readline()
    sep = ";" if ";" in first else ","
    return pd.read_csv(path, sep=sep, encoding="utf-8", on_bad_lines="skip", engine="python")


def _parse_mt4_dot_dates(series: pd.Series) -> pd.Series:
    """Chuỗi dạng `2004.06.11 07:15` → datetime UTC."""
    t = series.astype(str).str.strip()
    iso_like = t.str.replace(r"^(\d{4})\.(\d{2})\.(\d{2})", r"\1-\2-\3", regex=True)
    return pd.to_datetime(iso_like, utc=True)


def _parse_time_column(raw_t: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(raw_t):
        return pd.to_datetime(raw_t, utc=True)
    if len(raw_t) == 0:
        return pd.to_datetime(raw_t, utc=True)
    s0 = str(raw_t.iloc[0])
    if len(s0) >= 10 and s0[4] == "." and s0[7] == ".":
        return _parse_mt4_dot_dates(raw_t)
    return pd.to_datetime(raw_t, utc=True)


def _standardize_ohlc_columns(df: pd.DataFrame) -> pd.DataFrame:
    cols = {c.lower().strip(): c for c in df.columns}
    tcol = cols.get("time") or cols.get("date") or cols.get("datetime")
    if tcol is None:
        raise ValueError("CSV must have time/date/datetime column")
    raw_t = df[tcol]
    time_utc = _parse_time_column(raw_t)
    out = pd.DataFrame({"time": time_utc})
    for c in ("open", "high", "low", "close"):
        if c not in {x.lower() for x in df.columns}:
            raise ValueError(f"Missing column: {c}")
        key = [x for x in df.columns if x.lower().strip() == c][0]
        out[c] = pd.to_numeric(df[key], errors="coerce").astype(float)
    col_lower = {x.lower().strip(): x for x in df.columns}
    for vk in ("volume", "tick_volume", "real_volume"):
        if vk in col_lower:
            out["volume"] = pd.to_numeric(df[col_lower[vk]], errors="coerce")
            break
    return out.dropna(subset=["open", "high", "low", "close"]).sort_values("time").reset_index(drop=True)


def load_ohlc_csv(path: str | Path) -> pd.DataFrame:
    """
    Load CSV: phẩy hoặc chấm phẩy; cột thời gian time/date/datetime.
    MT4 export: `Date;Open;High;Low;Close;Volume`.
    """
    p = Path(path)
    df = _read_csv_flexible(p)
    return _standardize_ohlc_columns(df)


def _ts_utc(x: str | pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(x)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts


def _is_date_only(s: str) -> bool:
    s = str(s).strip()
    return len(s) <= 10 and "T" not in s and s.count(":") == 0


def slice_ohlc_by_window(
    df: pd.DataFrame,
    *,
    from_date: str | pd.Timestamp | None = None,
    to_date: str | pd.Timestamp | None = None,
    max_bars: int | None = None,
    tail: bool = True,
) -> pd.DataFrame:
    """
    Lọc theo khoảng thời gian và/hoặc giữ tối đa `max_bars` nến (mặc định lấy **cuối** chuỗi).

    `from_date` / `to_date`: ISO `YYYY-MM-DD` (cả ngày) hoặc có giờ; UTC.
    Nếu chỉ truyền ngày (`YYYY-MM-DD`), `to_date` bao gồm hết ngày đó (exclusive end+1d).
    """
    out = df.sort_values("time").reset_index(drop=True)
    if from_date is not None:
        ts = _ts_utc(from_date)
        out = out[out["time"] >= ts]
    if to_date is not None:
        raw = str(to_date).strip()
        if isinstance(to_date, str) and _is_date_only(raw):
            ts_end = _ts_utc(raw) + pd.Timedelta(days=1)
            out = out[out["time"] < ts_end]
        else:
            ts = _ts_utc(to_date)
            out = out[out["time"] <= ts]
    out = out.reset_index(drop=True)
    if max_bars is not None and len(out) > max_bars:
        out = out.tail(max_bars).reset_index(drop=True) if tail else out.head(max_bars).reset_index(drop=True)
    return out


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


def build_mtf_h1_m5(m5: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Chuẩn bị H1 + M5 từ chuỗi nến M5 (resample H1)."""
    m5 = m5.sort_values("time").reset_index(drop=True)
    h1 = resample_ohlc(m5, "1h")
    return {"M5": m5, "H1": h1}
