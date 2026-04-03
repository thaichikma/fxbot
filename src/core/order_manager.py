"""
Order manager — execute signals, partial TP, breakeven, trailing (MT5).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from src.data.models import Direction, Signal, TradeStatus
from src.risk.daily_tracker import DailyTracker
from src.risk.ftmo_guardian import FTMOGuardian
from src.risk.risk_manager import RiskManager

# MetaTrader 5 TRADE_RETCODE_DONE
RETCODE_DONE = 10009


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class OrderManager:
    """Execute and manage positions."""

    def __init__(
        self,
        mt5_client: Any,
        guardian: FTMOGuardian,
        risk_manager: RiskManager,
        db: Any,
        tracker: DailyTracker,
        settings: dict,
    ):
        self._mt5 = mt5_client
        self._guardian = guardian
        self._risk = risk_manager
        self._db = db
        self._tracker = tracker
        self._settings = settings
        self._strategy = settings.get("strategy", {})

    def _max_spread(self, symbol: str) -> int:
        for p in self._settings.get("pairs", []):
            if p.get("symbol") == symbol:
                return int(p.get("max_spread_points", 0))
        return 0

    def _current_spread_points(self, symbol: str) -> int:
        info = self._mt5.get_symbol_info(symbol)
        if info is None:
            return 0
        sp = getattr(info, "spread_points", None)
        if sp is not None:
            return int(sp)
        return int(getattr(info, "spread", 0) or 0)

    async def execute_signal(self, signal: Signal, risk_pct: float) -> dict[str, Any] | None:
        """Open market position from signal."""
        account = self._mt5.get_account_info()
        equity = float(account.equity)
        balance = float(account.balance)

        spread_pts = self._current_spread_points(signal.symbol)
        max_sp = self._max_spread(signal.symbol)

        positions = self._mt5.get_positions()
        ok_pos, reason_pos = self._guardian.check_positions_limit(len(positions))
        if not ok_pos:
            logger.warning("Order blocked | {}", reason_pos)
            return None

        ok_corr, reason_corr = self._risk.check_correlation(signal, positions)
        if not ok_corr:
            logger.warning("Order blocked | {}", reason_corr)
            return None

        lot = self._risk.calculate_lot_size_with_risk_override(
            signal.symbol, signal.sl_distance_pips, balance, risk_pct
        )

        approved, reason = self._guardian.can_open_trade(
            signal, lot, equity, spread_pts, max_sp
        )
        if not approved:
            logger.warning("Guardian veto | {}", reason)
            return None

        direction = "BUY" if signal.direction == Direction.BUY else "SELL"
        res = self._mt5.send_market_order(
            symbol=signal.symbol,
            direction=direction,
            lot_size=lot,
            sl=signal.stop_loss,
            tp=signal.take_profit_1,
            comment=f"FXBot {signal.signal_type.value}",
        )

        if res.get("retcode") != RETCODE_DONE:
            logger.error("Order failed | {}", res)
            return None

        ticket = int(res.get("order") or res.get("deal") or 0)
        fill = float(res.get("price", signal.entry_price))

        trade_id = str(uuid.uuid4())
        row = {
            "id": trade_id,
            "ticket": ticket,
            "signal_id": signal.id,
            "symbol": signal.symbol,
            "direction": signal.direction.value,
            "lot_size": lot,
            "entry_price": fill,
            "stop_loss": signal.stop_loss,
            "take_profit_1": signal.take_profit_1,
            "take_profit_2": signal.take_profit_2,
            "take_profit_3": signal.take_profit_3,
            "current_sl": signal.stop_loss,
            "remaining_lot": lot,
            "tp1_hit": 0,
            "tp2_hit": 0,
            "tp3_hit": 0,
            "breakeven_applied": 0,
            "trailing_active": 0,
            "open_time": _utc_now_iso(),
            "close_time": None,
            "close_price": 0.0,
            "pnl": 0.0,
            "pnl_pips": 0.0,
            "status": TradeStatus.OPEN.value,
            "session": signal.session,
            "signal_type": signal.signal_type.value,
        }

        await self._db.insert_trade(row)
        self._tracker.record_trade_opened()
        logger.info("Trade opened | {} {} | ticket={}", signal.symbol, direction, ticket)
        return row

    def _tp_portions(self) -> list[float]:
        p = self._strategy.get("tp_portions") or [0.5, 0.3, 0.2]
        return [float(x) for x in p]

    async def manage_open_trades(self) -> None:
        """Partial TP, breakeven, optional trailing."""
        trades = await self._db.get_open_trades()
        if not trades:
            return

        pos_by_ticket = {p["ticket"]: p for p in self._mt5.get_positions()}
        portions = self._tp_portions()
        breakeven = bool(self._strategy.get("breakeven_at_tp1", True))
        trail_after_tp2 = bool(self._strategy.get("trailing_after_tp2", True))

        for tr in trades:
            ticket = int(tr.get("ticket", 0))
            pos = pos_by_ticket.get(ticket)
            if not pos:
                continue

            sym = tr["symbol"]
            direction = tr["direction"]
            price = float(pos.get("price_current", 0) or pos.get("price_open", 0))
            initial_lot = float(tr["lot_size"])
            rem = float(tr.get("remaining_lot", initial_lot))
            if rem <= 0:
                continue

            tp1 = float(tr["take_profit_1"])
            tp2 = float(tr.get("take_profit_2", 0))
            tp3 = float(tr.get("take_profit_3", 0))
            entry = float(tr["entry_price"])

            tp1_hit = bool(int(tr.get("tp1_hit", 0) or 0))
            tp2_hit = bool(int(tr.get("tp2_hit", 0) or 0))

            hit1 = (direction == "BUY" and price >= tp1) or (direction == "SELL" and price <= tp1)
            hit2 = tp2 > 0 and ((direction == "BUY" and price >= tp2) or (direction == "SELL" and price <= tp2))
            hit3 = tp3 > 0 and ((direction == "BUY" and price >= tp3) or (direction == "SELL" and price <= tp3))

            if not tp1_hit and hit1 and len(portions) > 0:
                close_vol = round(initial_lot * portions[0], 2)
                close_vol = min(close_vol, rem)
                if close_vol > 0:
                    r = self._mt5.close_position(ticket, close_vol)
                    if r.get("retcode") == RETCODE_DONE:
                        new_rem = round(rem - close_vol, 2)
                        upd: dict[str, Any] = {"tp1_hit": 1, "remaining_lot": new_rem}
                        if breakeven:
                            upd["current_sl"] = entry
                            upd["breakeven_applied"] = 1
                            self._mt5.modify_position(ticket, sl=entry, tp=float(tp2 or 0))
                        await self._db.update_trade(tr["id"], upd)
                        logger.info("TP1 partial | ticket={} | closed={}", ticket, close_vol)
                continue

            if not tp1_hit:
                continue

            if not tp2_hit and hit2 and len(portions) > 1:
                rem = float(tr.get("remaining_lot", initial_lot))
                close_vol = round(initial_lot * portions[1], 2)
                close_vol = min(close_vol, rem)
                if close_vol > 0:
                    r = self._mt5.close_position(ticket, close_vol)
                    if r.get("retcode") == RETCODE_DONE:
                        new_rem = round(rem - close_vol, 2)
                        upd = {"tp2_hit": 1, "remaining_lot": new_rem}
                        if trail_after_tp2:
                            upd["trailing_active"] = 1
                        await self._db.update_trade(tr["id"], upd)
                        logger.info("TP2 partial | ticket={} | closed={}", ticket, close_vol)
                continue

            if not tp2_hit:
                continue

            if hit3 and len(portions) > 2:
                rem = float(tr.get("remaining_lot", initial_lot))
                close_vol = rem
                if close_vol > 0:
                    r = self._mt5.close_position(ticket, close_vol)
                    if r.get("retcode") == RETCODE_DONE:
                        profit = float(pos.get("profit", 0) or 0)
                        await self._db.update_trade(
                            tr["id"],
                            {
                                "tp3_hit": 1,
                                "remaining_lot": 0,
                                "status": TradeStatus.CLOSED.value,
                                "close_time": _utc_now_iso(),
                                "pnl": profit,
                            },
                        )
                        self._tracker.record_trade_closed(profit)
                        logger.info("TP3 full close | ticket={}", ticket)

    async def close_all_positions(self) -> list[str]:
        """Emergency close all (used by /kill)."""
        msgs: list[str] = []
        for p in self._mt5.get_positions():
            t = int(p["ticket"])
            r = self._mt5.close_position(t)
            msgs.append(f"{t}: {r.get('comment', r)}")
        return msgs
