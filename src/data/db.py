"""
SQLite database layer with async support.

Tables:
- trades: Executed trade records
- signals: Generated signal history
- daily_pnl: Daily performance snapshots
- config_state: Runtime state persistence (key-value)
- ohlc_bars: OHLC đa khung (symbol, tf, ts) — giả lập / phân tích trend
- simulation_runs, simulation_steps: bản ghi walk-forward + metrics JSON
"""

import aiosqlite
from pathlib import Path
from loguru import logger

from src.data.mtf_schema import MTF_FULL_SCHEMA

# SQL for table creation
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS trades (
    id TEXT PRIMARY KEY,
    ticket INTEGER,
    signal_id TEXT,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    lot_size REAL NOT NULL,
    entry_price REAL NOT NULL,
    stop_loss REAL NOT NULL,
    take_profit_1 REAL DEFAULT 0,
    take_profit_2 REAL DEFAULT 0,
    take_profit_3 REAL DEFAULT 0,
    current_sl REAL DEFAULT 0,
    remaining_lot REAL DEFAULT 0,
    tp1_hit INTEGER DEFAULT 0,
    tp2_hit INTEGER DEFAULT 0,
    tp3_hit INTEGER DEFAULT 0,
    breakeven_applied INTEGER DEFAULT 0,
    trailing_active INTEGER DEFAULT 0,
    open_time TEXT NOT NULL,
    close_time TEXT,
    close_price REAL DEFAULT 0,
    pnl REAL DEFAULT 0,
    pnl_pips REAL DEFAULT 0,
    status TEXT DEFAULT 'open',
    session TEXT,
    signal_type TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS signals (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    entry_price REAL NOT NULL,
    stop_loss REAL NOT NULL,
    take_profit_1 REAL DEFAULT 0,
    take_profit_2 REAL DEFAULT 0,
    take_profit_3 REAL DEFAULT 0,
    h4_bias TEXT,
    h1_structure TEXT,
    session TEXT,
    sl_distance_pips REAL DEFAULT 0,
    risk_reward_ratio REAL DEFAULT 0,
    timeframe TEXT DEFAULT 'M15',
    confidence REAL DEFAULT 50,
    created_at TEXT NOT NULL,
    expiry TEXT,
    status TEXT DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS daily_pnl (
    date TEXT PRIMARY KEY,
    starting_balance REAL NOT NULL,
    ending_balance REAL DEFAULT 0,
    realized_pnl REAL DEFAULT 0,
    unrealized_pnl REAL DEFAULT 0,
    max_equity REAL DEFAULT 0,
    min_equity REAL DEFAULT 0,
    trade_count INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    request_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS config_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_open_time ON trades(open_time);
CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);
CREATE INDEX IF NOT EXISTS idx_signals_created ON signals(created_at);
CREATE INDEX IF NOT EXISTS idx_daily_pnl_date ON daily_pnl(date);
"""

# OHLC đa khung + simulation (giả lập / đánh giá trend)
SCHEMA_SQL += "\n" + MTF_FULL_SCHEMA


class Database:
    """Async SQLite database manager."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Create database and tables."""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row  # type: ignore
        await self._db.executescript(SCHEMA_SQL)
        await self._db.commit()
        logger.info("Database initialized at {}", self.db_path)

    async def close(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()
            logger.info("Database closed")

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self._db

    # ─── Trade CRUD ───────────────────────────────────────────

    async def insert_trade(self, trade: dict) -> None:
        """Insert a new trade record."""
        cols = ", ".join(trade.keys())
        placeholders = ", ".join(["?"] * len(trade))
        sql = f"INSERT INTO trades ({cols}) VALUES ({placeholders})"
        await self.db.execute(sql, list(trade.values()))
        await self.db.commit()

    async def update_trade(self, trade_id: str, updates: dict) -> None:
        """Update trade fields by ID."""
        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        sql = f"UPDATE trades SET {set_clause} WHERE id = ?"
        await self.db.execute(sql, [*updates.values(), trade_id])
        await self.db.commit()

    async def get_open_trades(self) -> list[dict]:
        """Get all open trades."""
        sql = "SELECT * FROM trades WHERE status IN ('open', 'partial_closed') ORDER BY open_time"
        cursor = await self.db.execute(sql)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_trades_by_date(self, date_str: str) -> list[dict]:
        """Get trades opened on a specific date (YYYY-MM-DD)."""
        sql = "SELECT * FROM trades WHERE date(open_time) = ? ORDER BY open_time"
        cursor = await self.db.execute(sql, [date_str])
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_closed_trades(self, limit: int = 50) -> list[dict]:
        """Get recent closed trades."""
        sql = "SELECT * FROM trades WHERE status IN ('closed', 'emergency_closed') ORDER BY close_time DESC LIMIT ?"
        cursor = await self.db.execute(sql, [limit])
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # ─── Signal CRUD ──────────────────────────────────────────

    async def insert_signal(self, signal: dict) -> None:
        """Insert a new signal."""
        cols = ", ".join(signal.keys())
        placeholders = ", ".join(["?"] * len(signal))
        sql = f"INSERT INTO signals ({cols}) VALUES ({placeholders})"
        await self.db.execute(sql, list(signal.values()))
        await self.db.commit()

    async def update_signal_status(self, signal_id: str, status: str) -> None:
        """Update signal status."""
        sql = "UPDATE signals SET status = ? WHERE id = ?"
        await self.db.execute(sql, [status, signal_id])
        await self.db.commit()

    async def has_similar_signal_recent(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        *,
        minutes: int = 30,
        price_epsilon: float = 1e-4,
    ) -> bool:
        """True if a comparable signal was stored recently (dedupe for Telegram)."""
        sql = """
            SELECT 1 FROM signals
            WHERE symbol = ? AND direction = ?
              AND datetime(created_at) > datetime('now', ?)
              AND ABS(entry_price - ?) < ?
            LIMIT 1
        """
        cursor = await self.db.execute(
            sql,
            [symbol, direction, f"-{int(minutes)} minutes", entry_price, price_epsilon],
        )
        row = await cursor.fetchone()
        return row is not None

    # ─── Daily PnL ────────────────────────────────────────────

    async def upsert_daily_pnl(self, data: dict) -> None:
        """Insert or update daily PnL record."""
        sql = """
            INSERT INTO daily_pnl (date, starting_balance, ending_balance,
                realized_pnl, unrealized_pnl, max_equity, min_equity,
                trade_count, winning_trades, losing_trades, request_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                ending_balance = excluded.ending_balance,
                realized_pnl = excluded.realized_pnl,
                unrealized_pnl = excluded.unrealized_pnl,
                max_equity = MAX(daily_pnl.max_equity, excluded.max_equity),
                min_equity = MIN(daily_pnl.min_equity, excluded.min_equity),
                trade_count = excluded.trade_count,
                winning_trades = excluded.winning_trades,
                losing_trades = excluded.losing_trades,
                request_count = excluded.request_count
        """
        await self.db.execute(sql, [
            data["date"], data["starting_balance"], data.get("ending_balance", 0),
            data.get("realized_pnl", 0), data.get("unrealized_pnl", 0),
            data.get("max_equity", 0), data.get("min_equity", 0),
            data.get("trade_count", 0), data.get("winning_trades", 0),
            data.get("losing_trades", 0), data.get("request_count", 0),
        ])
        await self.db.commit()

    async def get_daily_pnl(self, date_str: str) -> dict | None:
        """Get daily PnL for a specific date."""
        sql = "SELECT * FROM daily_pnl WHERE date = ?"
        cursor = await self.db.execute(sql, [date_str])
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_positive_days_total(self) -> float:
        """Sum of all positive days' profit (for best day rule)."""
        sql = "SELECT COALESCE(SUM(realized_pnl), 0) as total FROM daily_pnl WHERE realized_pnl > 0"
        cursor = await self.db.execute(sql)
        row = await cursor.fetchone()
        return row["total"] if row else 0.0

    async def get_trading_days_count(self) -> int:
        """Count of days with at least 1 trade."""
        sql = "SELECT COUNT(*) as count FROM daily_pnl WHERE trade_count > 0"
        cursor = await self.db.execute(sql)
        row = await cursor.fetchone()
        return row["count"] if row else 0

    async def get_all_daily_pnl(self) -> list[dict]:
        """Get all daily PnL records."""
        sql = "SELECT * FROM daily_pnl ORDER BY date"
        cursor = await self.db.execute(sql)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # ─── Config State ─────────────────────────────────────────

    async def set_state(self, key: str, value: str) -> None:
        """Set or update a config state value."""
        sql = """
            INSERT INTO config_state (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
        """
        await self.db.execute(sql, [key, value])
        await self.db.commit()

    async def get_state(self, key: str, default: str = "") -> str:
        """Get a config state value."""
        sql = "SELECT value FROM config_state WHERE key = ?"
        cursor = await self.db.execute(sql, [key])
        row = await cursor.fetchone()
        return row["value"] if row else default
