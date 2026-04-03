"""
MT5 Mock Client — for development on Mac/Linux.

Same interface as MT5Client but uses synthetic data.
Supports:
- Loading historical data from CSV files
- Simulated order execution
- Virtual account tracking
- Test scenario injection
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger

from src.data.models import AccountInfo, SymbolInfo, Tick


class MT5Mock:
    """
    Mock MT5 client for development on non-Windows platforms.
    Implements the same interface as MT5Client.
    """

    def __init__(
        self,
        initial_balance: float = 10000.0,
        magic_number: int = 20260403,
        **kwargs,
    ):
        self.magic_number = magic_number
        self._connected = False
        self._request_count = 0
        self._last_reset_date: str = ""

        # Virtual account
        self._balance = initial_balance
        self._equity = initial_balance
        self._profit = 0.0

        # Virtual positions
        self._positions: dict[int, dict] = {}
        self._next_ticket = 100001

        # Price simulation
        self._prices: dict[str, float] = {
            "XAUUSD": 2650.00,
            "EURUSD": 1.0850,
            "GBPUSD": 1.2650,
            "USDJPY": 150.50,
        }

        logger.info("MT5Mock initialized | balance={}", initial_balance)

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def request_count(self) -> int:
        return self._request_count

    def _count_request(self) -> None:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if today != self._last_reset_date:
            self._request_count = 0
            self._last_reset_date = today
        self._request_count += 1

    # ─── Connection ───────────────────────────────────────────

    def initialize(self) -> bool:
        self._connected = True
        logger.info("MT5Mock connected | balance={}", self._balance)
        return True

    def shutdown(self) -> None:
        self._connected = False
        logger.info("MT5Mock disconnected")

    def reconnect(self, max_retries: int = 3) -> bool:
        self._connected = True
        return True

    # ─── Data ─────────────────────────────────────────────────

    def get_account_info(self) -> AccountInfo:
        self._count_request()
        # Recalculate equity from open positions
        unrealized = sum(p.get("profit", 0) for p in self._positions.values())
        self._equity = self._balance + unrealized
        self._profit = unrealized

        return AccountInfo(
            login=99999999,
            balance=self._balance,
            equity=self._equity,
            margin=0.0,
            free_margin=self._equity,
            margin_level=0.0,
            profit=self._profit,
            currency="USD",
            leverage=100,
            server="MOCK-Demo",
            name="Mock Trader",
        )

    def ensure_symbol_ready(self, symbol: str) -> bool:
        """Mock: luôn OK để tải dữ liệu giả lập."""
        return True

    def get_symbol_info(self, symbol: str) -> SymbolInfo | None:
        self._count_request()
        configs = {
            "XAUUSD": SymbolInfo(
                symbol="XAUUSD", description="Gold", contract_size=100,
                pip_size=0.10, pip_value_per_lot=1.0, point_size=0.01,
                digits=2, bid=self._prices.get("XAUUSD", 2650),
                ask=self._prices.get("XAUUSD", 2650) + 0.30,
                spread_points=30,
            ),
            "EURUSD": SymbolInfo(
                symbol="EURUSD", description="Euro/USD", contract_size=100000,
                pip_size=0.0001, pip_value_per_lot=10.0, point_size=0.00001,
                digits=5, bid=self._prices.get("EURUSD", 1.085),
                ask=self._prices.get("EURUSD", 1.085) + 0.0001,
                spread_points=10,
            ),
            "GBPUSD": SymbolInfo(
                symbol="GBPUSD", description="GBP/USD", contract_size=100000,
                pip_size=0.0001, pip_value_per_lot=10.0, point_size=0.00001,
                digits=5, bid=self._prices.get("GBPUSD", 1.265),
                ask=self._prices.get("GBPUSD", 1.265) + 0.00015,
                spread_points=15,
            ),
            "USDJPY": SymbolInfo(
                symbol="USDJPY", description="USD/JPY", contract_size=100000,
                pip_size=0.01, pip_value_per_lot=6.67, point_size=0.001,
                digits=3, bid=self._prices.get("USDJPY", 150.50),
                ask=self._prices.get("USDJPY", 150.50) + 0.012,
                spread_points=12,
            ),
        }
        return configs.get(symbol)

    def get_rates(
        self,
        symbol: str,
        timeframe: str,
        count: int = 500,
    ) -> pd.DataFrame | None:
        """Generate synthetic OHLCV data using random walk."""
        self._count_request()

        base_price = self._prices.get(symbol, 1.0)
        pip_size = {"XAUUSD": 0.10, "USDJPY": 0.01}.get(symbol, 0.0001)

        # Timeframe to minutes
        tf_minutes = {
            "M1": 1, "M5": 5, "M15": 15, "M30": 30,
            "H1": 60, "H4": 240, "D1": 1440, "W1": 10080,
        }.get(timeframe, 60)

        # Generate random walk
        np.random.seed(hash(f"{symbol}_{timeframe}") % 2**32)
        returns = np.random.normal(0, pip_size * 5, count)
        prices = base_price + np.cumsum(returns)

        # Generate OHLCV
        now = datetime.utcnow()
        data = []
        for i in range(count):
            bar_time = now - timedelta(minutes=tf_minutes * (count - i))
            o = prices[i]
            h = o + abs(np.random.normal(0, pip_size * 10))
            l = o - abs(np.random.normal(0, pip_size * 10))
            c = o + np.random.normal(0, pip_size * 3)
            v = int(abs(np.random.normal(1000, 500)))
            data.append({
                "time": bar_time,
                "open": round(o, 5),
                "high": round(max(o, h, c), 5),
                "low": round(min(o, l, c), 5),
                "close": round(c, 5),
                "tick_volume": v,
                "spread": 10,
                "real_volume": 0,
            })

        return pd.DataFrame(data)

    def get_tick(self, symbol: str) -> Tick | None:
        self._count_request()
        price = self._prices.get(symbol, 1.0)
        spread = {"XAUUSD": 0.30, "EURUSD": 0.0001, "GBPUSD": 0.00015, "USDJPY": 0.012}.get(symbol, 0.0001)
        return Tick(
            symbol=symbol,
            bid=price,
            ask=price + spread,
            time=datetime.utcnow(),
        )

    # ─── Orders ───────────────────────────────────────────────

    def order_send(self, request: dict) -> dict:
        self._count_request()
        # Simulate instant fill
        return {"retcode": 10009, "order": self._next_ticket, "deal": self._next_ticket,
                "volume": request.get("volume", 0), "price": request.get("price", 0),
                "comment": "Mock order executed"}

    def send_market_order(
        self,
        symbol: str,
        direction: str,
        lot_size: float,
        sl: float = 0.0,
        tp: float = 0.0,
        comment: str = "",
    ) -> dict:
        self._count_request()
        price = self._prices.get(symbol, 1.0)
        spread = {"XAUUSD": 0.30, "EURUSD": 0.0001, "GBPUSD": 0.00015, "USDJPY": 0.012}.get(symbol, 0.0001)

        fill_price = price + spread if direction == "BUY" else price
        ticket = self._next_ticket
        self._next_ticket += 1

        self._positions[ticket] = {
            "ticket": ticket,
            "symbol": symbol,
            "type": direction,
            "volume": lot_size,
            "price_open": fill_price,
            "sl": sl,
            "tp": tp,
            "price_current": fill_price,
            "profit": 0.0,
            "time": datetime.utcnow(),
            "magic": self.magic_number,
            "comment": comment or f"FXBot Mock {direction}",
        }

        logger.info("Mock order: {} {} {} @ {} | SL={} TP={} | ticket={}",
                     direction, lot_size, symbol, fill_price, sl, tp, ticket)

        return {
            "retcode": 10009,
            "order": ticket,
            "deal": ticket,
            "volume": lot_size,
            "price": fill_price,
            "comment": "Mock order executed",
        }

    def close_position(self, ticket: int, lot_size: Optional[float] = None) -> dict:
        self._count_request()
        if ticket not in self._positions:
            return {"retcode": -1, "comment": f"Position {ticket} not found"}

        pos = self._positions[ticket]
        close_lot = lot_size if lot_size else pos["volume"]

        # Simulate PnL
        pnl = pos.get("profit", 0) * (close_lot / pos["volume"])
        self._balance += pnl

        if close_lot >= pos["volume"]:
            del self._positions[ticket]
        else:
            pos["volume"] -= close_lot

        logger.info("Mock close: ticket={} lot={} pnl={:.2f}", ticket, close_lot, pnl)
        return {"retcode": 10009, "order": ticket, "comment": "Mock close executed"}

    def modify_position(self, ticket: int, sl: float = 0.0, tp: float = 0.0) -> dict:
        self._count_request()
        if ticket not in self._positions:
            return {"retcode": -1, "comment": f"Position {ticket} not found"}

        if sl:
            self._positions[ticket]["sl"] = sl
        if tp:
            self._positions[ticket]["tp"] = tp

        logger.debug("Mock modify: ticket={} sl={} tp={}", ticket, sl, tp)
        return {"retcode": 10009, "comment": "Mock modify executed"}

    def get_positions(self, symbol: Optional[str] = None) -> list[dict]:
        self._count_request()
        positions = list(self._positions.values())
        if symbol:
            positions = [p for p in positions if p["symbol"] == symbol]
        return [p for p in positions if p.get("magic") == self.magic_number]

    # ─── Mock Controls ────────────────────────────────────────

    def set_price(self, symbol: str, price: float) -> None:
        """Manually set price (for testing)."""
        self._prices[symbol] = price
        # Update open positions
        for pos in self._positions.values():
            if pos["symbol"] == symbol:
                contract_size = {"XAUUSD": 100, "USDJPY": 100000}.get(symbol, 100000)
                if pos["type"] == "BUY":
                    pos["profit"] = (price - pos["price_open"]) * pos["volume"] * contract_size
                else:
                    pos["profit"] = (pos["price_open"] - price) * pos["volume"] * contract_size
                pos["price_current"] = price
