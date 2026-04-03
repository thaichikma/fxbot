"""
MT5 Client — MetaTrader 5 connection and data wrapper.

This module wraps the official MetaTrader5 Python package.
Only runs on Windows. On Mac/Linux, use MT5Mock instead.

Provides:
- Connection management with auto-reconnect
- OHLCV data fetching (multi-timeframe)
- Account info queries
- Order execution (market, limit, stop)
- Position management (close, modify)
- Request counting (for FTMO hyperactivity limit)
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from typing import Optional

import pandas as pd
from loguru import logger

from src.data.models import AccountInfo, SymbolInfo, Tick

# Timeframe mapping
TIMEFRAME_MAP = {
    "M1": None, "M5": None, "M15": None, "M30": None,
    "H1": None, "H4": None, "D1": None, "W1": None, "MN1": None,
}

# Only import MetaTrader5 on Windows
if sys.platform == "win32":
    try:
        import MetaTrader5 as mt5

        # Monthly: official API uses TIMEFRAME_MN1; older snippets used TIMEFRAME_MN.
        _mn = getattr(mt5, "TIMEFRAME_MN1", None) or getattr(mt5, "TIMEFRAME_MN", None)
        if _mn is None:
            logger.warning("MetaTrader5: no monthly timeframe constant (TIMEFRAME_MN1/MN); MN1 disabled")
        TIMEFRAME_MAP = {
            "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1, "W1": mt5.TIMEFRAME_W1,
            "MN1": _mn,
        }
    except ImportError:
        mt5 = None  # type: ignore
        logger.warning("MetaTrader5 package not available")
else:
    mt5 = None  # type: ignore
    logger.info("Non-Windows platform: MT5 client will not work. Use MT5Mock.")


class MT5Client:
    """
    MetaTrader 5 client wrapper.

    Usage:
        client = MT5Client(login=123, password="xxx", server="FTMO-Demo")
        if client.initialize():
            rates = client.get_rates("XAUUSD", "H1", 100)
            client.shutdown()
    """

    def __init__(
        self,
        login: int = 0,
        password: str = "",
        server: str = "",
        path: str = "",
        magic_number: int = 20260403,
        deviation: int = 20,
        filling_type: str = "ioc",
    ):
        self.login = login
        self.password = password
        self.server = server
        self.path = path
        self.magic_number = magic_number
        self.deviation = deviation
        self.filling_type = filling_type
        self._connected = False
        self._request_count = 0
        self._last_reset_date: str = ""

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def request_count(self) -> int:
        return self._request_count

    def _count_request(self) -> None:
        """Increment daily request counter."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if today != self._last_reset_date:
            self._request_count = 0
            self._last_reset_date = today
        self._request_count += 1

    def _get_filling_type(self):
        """Get MT5 filling type constant."""
        if mt5 is None:
            return 0
        mapping = {
            "ioc": mt5.ORDER_FILLING_IOC,
            "fok": mt5.ORDER_FILLING_FOK,
            "return": mt5.ORDER_FILLING_RETURN,
        }
        return mapping.get(self.filling_type, mt5.ORDER_FILLING_IOC)

    # ─── Connection ───────────────────────────────────────────

    def initialize(self) -> bool:
        """Initialize MT5 terminal connection."""
        if mt5 is None:
            logger.error("MT5 not available on this platform")
            return False

        kwargs = {}
        if self.path:
            kwargs["path"] = self.path
        if self.login:
            kwargs["login"] = self.login
            kwargs["password"] = self.password
            kwargs["server"] = self.server

        if not mt5.initialize(**kwargs):
            error = mt5.last_error()
            logger.error("MT5 initialize failed: {}", error)
            return False

        self._connected = True
        info = mt5.account_info()
        logger.info(
            "MT5 connected | login={} | server={} | balance={}",
            info.login, info.server, info.balance,
        )
        return True

    def shutdown(self) -> None:
        """Shutdown MT5 connection."""
        if mt5 is not None and self._connected:
            mt5.shutdown()
            self._connected = False
            logger.info("MT5 disconnected")

    def reconnect(self, max_retries: int = 3) -> bool:
        """Attempt to reconnect with exponential backoff."""
        for attempt in range(1, max_retries + 1):
            logger.warning("MT5 reconnect attempt {}/{}", attempt, max_retries)
            self.shutdown()
            time.sleep(2 ** attempt)
            if self.initialize():
                return True
        logger.critical("MT5 reconnection failed after {} attempts", max_retries)
        return False

    # ─── Data ─────────────────────────────────────────────────

    def get_account_info(self) -> AccountInfo:
        """Get current account information."""
        if mt5 is None or not self._connected:
            return AccountInfo()

        self._count_request()
        info = mt5.account_info()
        if info is None:
            logger.error("Failed to get account info: {}", mt5.last_error())
            return AccountInfo()

        return AccountInfo(
            login=info.login,
            balance=info.balance,
            equity=info.equity,
            margin=info.margin,
            free_margin=info.margin_free,
            margin_level=info.margin_level if info.margin_level else 0.0,
            profit=info.profit,
            currency=info.currency,
            leverage=info.leverage,
            server=info.server,
            name=info.name,
        )

    def get_symbol_info(self, symbol: str) -> SymbolInfo | None:
        """Get symbol specification from MT5."""
        if mt5 is None or not self._connected:
            return None

        self._count_request()
        info = mt5.symbol_info(symbol)
        if info is None:
            # Try selecting the symbol first
            mt5.symbol_select(symbol, True)
            info = mt5.symbol_info(symbol)
            if info is None:
                logger.error("Symbol not found: {}", symbol)
                return None

        return SymbolInfo(
            symbol=info.name,
            description=info.description,
            contract_size=info.trade_contract_size,
            point_size=info.point,
            digits=info.digits,
            min_volume=info.volume_min,
            volume_step=info.volume_step,
            max_volume=info.volume_max,
            bid=info.bid,
            ask=info.ask,
            spread_points=info.spread,
        )

    def get_rates(
        self,
        symbol: str,
        timeframe: str,
        count: int = 500,
    ) -> pd.DataFrame | None:
        """
        Fetch OHLCV data as pandas DataFrame.

        Args:
            symbol: e.g. "XAUUSD"
            timeframe: "M1","M5","M15","M30","H1","H4","D1","W1"
            count: Number of bars to fetch

        Returns:
            DataFrame with columns: [time, open, high, low, close, tick_volume, spread, real_volume]
        """
        if mt5 is None or not self._connected:
            return None

        tf = TIMEFRAME_MAP.get(timeframe)
        if tf is None:
            logger.error("Invalid timeframe: {}", timeframe)
            return None

        self._count_request()
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)

        if rates is None or len(rates) == 0:
            logger.error("Failed to get rates for {} {}: {}", symbol, timeframe, mt5.last_error())
            return None

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df

    def get_tick(self, symbol: str) -> Tick | None:
        """Get latest tick for symbol."""
        if mt5 is None or not self._connected:
            return None

        self._count_request()
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None

        return Tick(
            symbol=symbol,
            bid=tick.bid,
            ask=tick.ask,
            time=datetime.utcfromtimestamp(tick.time),
            volume=tick.volume,
        )

    # ─── Orders ───────────────────────────────────────────────

    def order_send(self, request: dict) -> dict:
        """
        Send order to MT5.

        Returns dict with: retcode, order (ticket), comment
        """
        if mt5 is None or not self._connected:
            return {"retcode": -1, "order": 0, "comment": "Not connected"}

        # Set defaults
        request.setdefault("magic", self.magic_number)
        request.setdefault("deviation", self.deviation)
        request.setdefault("type_filling", self._get_filling_type())
        request.setdefault("type_time", mt5.ORDER_TIME_GTC)

        self._count_request()
        result = mt5.order_send(request)

        if result is None:
            error = mt5.last_error()
            logger.error("order_send failed: {}", error)
            return {"retcode": -1, "order": 0, "comment": str(error)}

        result_dict = {
            "retcode": result.retcode,
            "order": result.order,
            "deal": result.deal,
            "volume": result.volume,
            "price": result.price,
            "comment": result.comment,
        }

        if result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info("Order executed: ticket={} | {}", result.order, result.comment)
        else:
            logger.error("Order failed: retcode={} | {}", result.retcode, result.comment)

        return result_dict

    def send_market_order(
        self,
        symbol: str,
        direction: str,
        lot_size: float,
        sl: float = 0.0,
        tp: float = 0.0,
        comment: str = "",
    ) -> dict:
        """Send a market order (buy or sell)."""
        if mt5 is None:
            return {"retcode": -1, "order": 0, "comment": "MT5 not available"}

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return {"retcode": -1, "order": 0, "comment": "Cannot get tick"}

        if direction == "BUY":
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
        else:
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot_size,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "comment": comment or f"FXBot {direction}",
        }

        return self.order_send(request)

    def close_position(self, ticket: int, lot_size: Optional[float] = None) -> dict:
        """Close a position (full or partial)."""
        if mt5 is None or not self._connected:
            return {"retcode": -1, "comment": "Not connected"}

        self._count_request()
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return {"retcode": -1, "comment": f"Position {ticket} not found"}

        pos = positions[0]
        close_lot = lot_size if lot_size else pos.volume

        if pos.type == mt5.ORDER_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = mt5.symbol_info_tick(pos.symbol).bid
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(pos.symbol).ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": close_lot,
            "type": order_type,
            "position": ticket,
            "price": price,
            "comment": "FXBot close",
        }

        return self.order_send(request)

    def modify_position(self, ticket: int, sl: float = 0.0, tp: float = 0.0) -> dict:
        """Modify SL/TP of an open position."""
        if mt5 is None or not self._connected:
            return {"retcode": -1, "comment": "Not connected"}

        self._count_request()
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "sl": sl,
            "tp": tp,
        }

        return self.order_send(request)

    def get_positions(self, symbol: Optional[str] = None) -> list[dict]:
        """Get open positions, optionally filtered by symbol."""
        if mt5 is None or not self._connected:
            return []

        self._count_request()
        if symbol:
            positions = mt5.positions_get(symbol=symbol)
        else:
            positions = mt5.positions_get()

        if positions is None:
            return []

        result = []
        for pos in positions:
            if pos.magic == self.magic_number:
                result.append({
                    "ticket": pos.ticket,
                    "symbol": pos.symbol,
                    "type": "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL",
                    "volume": pos.volume,
                    "price_open": pos.price_open,
                    "sl": pos.sl,
                    "tp": pos.tp,
                    "price_current": pos.price_current,
                    "profit": pos.profit,
                    "time": datetime.utcfromtimestamp(pos.time),
                    "magic": pos.magic,
                    "comment": pos.comment,
                })
        return result
