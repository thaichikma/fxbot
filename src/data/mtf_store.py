"""
Lưu trữ & đọc OHLC đa khung (SQLite đồng bộ) phục vụ giả lập / phân tích trend.

Dùng cùng schema với `mtf_schema.MTF_FULL_SCHEMA`. Backtest có thể gọi trực tiếp
(không cần asyncio) để nạp H1/H4/M15… theo mốc thời gian.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from src.data.mtf_schema import MTF_FULL_SCHEMA


class MTFOHLCStore:
    """
    Kho OHLC đa khung — insert bulk từ DataFrame / CSV đã chuẩn hóa (time UTC).

    Ví dụ truy vấn “tại thời điểm t” cho SMC:
        store.frames_up_to("XAUUSD", t, need=("H4", "H1", "M15"))
    """

    def __init__(self, db_path: str | Path):
        self.db_path = str(Path(db_path).resolve())

    def connect(self) -> sqlite3.Connection:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_schema(self, conn: sqlite3.Connection | None = None) -> None:
        own = conn is None
        if own:
            conn = self.connect()
        try:
            conn.executescript(MTF_FULL_SCHEMA)
            conn.commit()
        finally:
            if own:
                conn.close()

    def insert_dataframe(
        self,
        df: pd.DataFrame,
        symbol: str,
        tf: str,
        *,
        source: str = "",
        replace: bool = False,
        chunk_size: int = 20_000,
    ) -> int:
        """
        Chèn cột time, open, high, low, close [, volume].

        `replace=True`: REPLACE INTO (ghi đè nến trùng khóa).
        """
        self.ensure_schema()
        cols = {c.lower(): c for c in df.columns}
        tcol = cols.get("time") or cols.get("date")
        if tcol is None:
            raise ValueError("DataFrame cần cột time")
        work = df[[tcol, "open", "high", "low", "close"]].copy()
        work.rename(columns={tcol: "time"}, inplace=True)
        vol_col = cols.get("volume") or cols.get("tick_volume")
        if vol_col and vol_col in df.columns:
            work["volume"] = pd.to_numeric(df[vol_col], errors="coerce")
        else:
            work["volume"] = None

        work["time"] = pd.to_datetime(work["time"], utc=True)

        op = "REPLACE" if replace else "INSERT OR IGNORE"
        sql = f"""
            {op} INTO ohlc_bars (symbol, tf, ts, open, high, low, close, volume, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        rows_out = 0
        conn = self.connect()
        try:
            batch: list[tuple] = []
            sym_u, tf_u = symbol.upper(), tf.upper()
            has_vol = "volume" in work.columns
            for i in range(len(work)):
                ts = pd.Timestamp(work["time"].iloc[i])
                if ts.tzinfo is None:
                    ts = ts.tz_localize("UTC")
                vol_v = None
                if has_vol:
                    vv = work["volume"].iloc[i]
                    vol_v = float(vv) if pd.notna(vv) else None
                batch.append(
                    (
                        sym_u,
                        tf_u,
                        ts.isoformat(),
                        float(work["open"].iloc[i]),
                        float(work["high"].iloc[i]),
                        float(work["low"].iloc[i]),
                        float(work["close"].iloc[i]),
                        vol_v,
                        source,
                    )
                )
                if len(batch) >= chunk_size:
                    conn.executemany(sql, batch)
                    rows_out += len(batch)
                    batch.clear()
            if batch:
                conn.executemany(sql, batch)
                rows_out += len(batch)
            conn.commit()
        finally:
            conn.close()
        logger.info("MTF store inserted {} rows | {} {}", rows_out, symbol, tf)
        return rows_out

    def fetch_range(
        self,
        symbol: str,
        tf: str,
        *,
        start: pd.Timestamp | str | None = None,
        end: pd.Timestamp | str | None = None,
    ) -> pd.DataFrame:
        """Lấy nến [start, end] theo UTC; end inclusive."""
        sym = symbol.upper()
        tfx = tf.upper()
        conds = ["symbol = ?", "tf = ?"]
        params: list[Any] = [sym, tfx]
        if start is not None:
            ts = pd.Timestamp(start)
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            conds.append("ts >= ?")
            params.append(ts.isoformat())
        if end is not None:
            ts = pd.Timestamp(end)
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            conds.append("ts <= ?")
            params.append(ts.isoformat())
        where = " AND ".join(conds)
        sql = f"SELECT ts, open, high, low, close, volume FROM ohlc_bars WHERE {where} ORDER BY ts ASC"
        conn = self.connect()
        try:
            cur = conn.execute(sql, params)
            data = cur.fetchall()
        finally:
            conn.close()
        if not data:
            return pd.DataFrame(columns=["time", "open", "high", "low", "close"])
        df = pd.DataFrame([dict(r) for r in data])
        df["time"] = pd.to_datetime(df["ts"], utc=True)
        base = ["time", "open", "high", "low", "close"]
        if "volume" in df.columns and df["volume"].notna().any():
            base.append("volume")
        return df[base].sort_values("time").reset_index(drop=True)

    def fetch_last_n(self, symbol: str, tf: str, n: int) -> pd.DataFrame:
        """Lấy `n` nến gần nhất (ASC theo thời gian)."""
        if n <= 0:
            return pd.DataFrame(columns=["time", "open", "high", "low", "close"])
        sym = symbol.upper()
        tfx = tf.upper()
        sql = """
            SELECT ts, open, high, low, close, volume FROM ohlc_bars
            WHERE symbol = ? AND tf = ?
            ORDER BY ts DESC
            LIMIT ?
        """
        conn = self.connect()
        try:
            cur = conn.execute(sql, [sym, tfx, n])
            data = cur.fetchall()
        finally:
            conn.close()
        if not data:
            return pd.DataFrame(columns=["time", "open", "high", "low", "close"])
        df = pd.DataFrame([dict(r) for r in data])
        df["time"] = pd.to_datetime(df["ts"], utc=True)
        base = ["time", "open", "high", "low", "close"]
        if "volume" in df.columns and df["volume"].notna().any():
            base.append("volume")
        out = df[base].sort_values("time").reset_index(drop=True)
        return out

    def frames_up_to(
        self,
        symbol: str,
        as_of: pd.Timestamp | str,
        *,
        need: tuple[str, ...] = ("H4", "H1", "M15"),
        min_rows: dict[str, int] | None = None,
    ) -> dict[str, pd.DataFrame]:
        """
        Trả về dict khung → OHLC chỉ gồm nến có `time <= as_of` (phục vụ SMC giống backtest).
        """
        t = pd.Timestamp(as_of)
        if t.tzinfo is None:
            t = t.tz_localize("UTC")
        defaults = {"H4": 10, "H1": 20, "M15": 50, "M30": 40, "M5": 200, "M1": 500, "D1": 5, "W1": 3, "MN1": 3}
        mr = {**defaults, **(min_rows or {})}
        out: dict[str, pd.DataFrame] = {}
        for tf in need:
            tfu = tf.upper()
            df = self.fetch_range(symbol, tfu, end=t)
            n = mr.get(tfu, 50)
            if len(df) > n:
                df = df.tail(n).reset_index(drop=True)
            out[tfu] = df
        return out

    def count_bars(self, symbol: str, tf: str) -> int:
        conn = self.connect()
        try:
            r = conn.execute(
                "SELECT COUNT(*) AS c FROM ohlc_bars WHERE symbol = ? AND tf = ?",
                [symbol.upper(), tf.upper()],
            ).fetchone()
            return int(r[0]) if r else 0
        finally:
            conn.close()

    def delete_symbol_tf(self, symbol: str, tf: str) -> None:
        conn = self.connect()
        try:
            conn.execute("DELETE FROM ohlc_bars WHERE symbol = ? AND tf = ?", [symbol.upper(), tf.upper()])
            conn.commit()
        finally:
            conn.close()

    # ─── Simulation run / steps (ghi metrics theo nến) ─────────────────

    def create_simulation_run(
        self,
        symbol: str,
        *,
        name: str = "",
        params: dict[str, Any] | None = None,
        notes: str = "",
    ) -> int:
        self.ensure_schema()
        conn = self.connect()
        try:
            cur = conn.execute(
                """
                INSERT INTO simulation_runs (name, symbol, params_json, notes)
                VALUES (?, ?, ?, ?)
                """,
                [name, symbol.upper(), json.dumps(params or {}), notes],
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def insert_simulation_step(
        self,
        run_id: int,
        bar_ts: pd.Timestamp | str,
        *,
        ref_tf: str = "M15",
        equity: float | None = None,
        balance: float | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        t = pd.Timestamp(bar_ts)
        if t.tzinfo is None:
            t = t.tz_localize("UTC")
        conn = self.connect()
        try:
            conn.execute(
                """
                INSERT INTO simulation_steps (run_id, bar_ts, ref_tf, equity, balance, metrics_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    run_id,
                    t.isoformat(),
                    ref_tf.upper(),
                    equity,
                    balance,
                    json.dumps(metrics or {}),
                ],
            )
            conn.commit()
        finally:
            conn.close()
