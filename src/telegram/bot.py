"""
Telegram Bot — Command handler and notification system.

Phase 1 shell with basic commands:
/start, /status, /help, /ping

Full command suite implemented in Phase 3.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Optional

from loguru import logger

try:
    from telegram import Update
    from telegram.ext import (
        Application,
        CommandHandler,
        ContextTypes,
    )
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False
    logger.warning("python-telegram-bot not installed — Telegram bot disabled")

if TYPE_CHECKING:
    from src.risk.ftmo_guardian import FTMOGuardian
    from src.risk.daily_tracker import DailyTracker


class TelegramBot:
    """
    Telegram bot for monitoring and controlling FXBot.

    Usage:
        bot = TelegramBot(token="xxx", chat_id="yyy")
        await bot.start()
        await bot.send_message("Hello!")
        await bot.stop()
    """

    def __init__(
        self,
        token: str = "",
        chat_id: str = "",
        guardian: Optional[FTMOGuardian] = None,
        tracker: Optional[DailyTracker] = None,
        mt5_client: Any = None,
    ):
        self.token = token
        self.chat_id = chat_id
        self.guardian = guardian
        self.tracker = tracker
        self.mt5_client = mt5_client
        self._app: Any = None
        self._running = False

        if not HAS_TELEGRAM:
            logger.warning("Telegram bot disabled — missing python-telegram-bot")

    async def start(self) -> None:
        """Start the Telegram bot."""
        if not HAS_TELEGRAM or not self.token:
            logger.warning("Telegram bot not started (missing token or package)")
            return

        self._app = Application.builder().token(self.token).build()
        self._register_handlers()

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        self._running = True
        logger.info("Telegram bot started")

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        if self._app and self._running:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            self._running = False
            logger.info("Telegram bot stopped")

    def _register_handlers(self) -> None:
        """Register command handlers."""
        if not self._app:
            return

        handlers = [
            CommandHandler("start", self._cmd_start),
            CommandHandler("help", self._cmd_help),
            CommandHandler("status", self._cmd_status),
            CommandHandler("ping", self._cmd_ping),
            CommandHandler("ftmo", self._cmd_ftmo),
            CommandHandler("kill", self._cmd_kill),
        ]
        for handler in handlers:
            self._app.add_handler(handler)

    # ─── Command Handlers ─────────────────────────────────────

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Welcome message."""
        msg = (
            "🤖 *FXBot MT5/FTMO*\n"
            "─────────────────\n"
            "Trading system active.\n\n"
            "Use /help for commands.\n"
            "Use /status for current state.\n"
            "Use /ftmo for challenge progress."
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """List all commands."""
        msg = (
            "📋 *Available Commands*\n"
            "─────────────────\n"
            "🔹 /status — Account status\n"
            "🔹 /ftmo — FTMO dashboard\n"
            "🔹 /ping — Check bot alive\n"
            "🔹 /kill — Emergency close all\n"
            "\n_More commands in Phase 3_"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Account status."""
        if not self.mt5_client:
            await update.message.reply_text("⚠️ MT5 not connected")
            return

        account = self.mt5_client.get_account_info()
        positions = self.mt5_client.get_positions()

        msg = (
            f"📊 *Account Status*\n"
            f"─────────────────\n"
            f"💰 Balance: ${account.balance:,.2f}\n"
            f"💎 Equity: ${account.equity:,.2f}\n"
            f"📈 Profit: ${account.profit:,.2f}\n"
            f"📊 Positions: {len(positions)}\n"
            f"🏦 Server: {account.server}\n"
        )

        if self.tracker:
            snapshot = self.tracker.get_snapshot()
            msg += (
                f"\n📅 *Today ({snapshot['date']})*\n"
                f"PnL: ${snapshot['daily_realized']:+.2f}\n"
                f"Trades: {snapshot['trade_count']} "
                f"(W:{snapshot['wins']} L:{snapshot['losses']})\n"
            )

        await update.message.reply_text(msg, parse_mode="Markdown")

    async def _cmd_ping(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Bot health check."""
        connected = self.mt5_client.connected if self.mt5_client else False
        kill = self.guardian.kill_switch_active if self.guardian else False

        status = "🟢 Online" if connected else "🔴 Disconnected"
        kill_status = "🔴 ACTIVE" if kill else "🟢 Off"

        msg = (
            f"🏓 *Pong!*\n"
            f"MT5: {status}\n"
            f"Kill Switch: {kill_status}\n"
            f"Requests: {self.mt5_client.request_count if self.mt5_client else 0}\n"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def _cmd_ftmo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """FTMO challenge dashboard."""
        if not self.guardian or not self.mt5_client:
            await update.message.reply_text("⚠️ Guardian not initialized")
            return

        equity = self.mt5_client.get_account_info().equity
        status = self.guardian.get_status(equity)

        kill_emoji = "🔴" if status["kill_switch"] else "🟢"

        msg = (
            f"🏛️ *FTMO Dashboard*\n"
            f"─────────────────\n"
            f"Kill Switch: {kill_emoji}\n\n"
            f"📅 *Daily Loss*\n"
            f"PnL: ${status['daily_pnl']:+.2f} ({status['daily_pnl_pct']:+.1f}%)\n"
            f"Limit: -${status['daily_limit']:.2f}\n"
            f"Usage: {status['daily_usage_pct']:.0f}%\n\n"
            f"📉 *Drawdown*\n"
            f"Equity: ${status['equity']:,.2f}\n"
            f"Min Equity: ${status['min_equity']:,.2f}\n"
            f"DD: {status['drawdown_pct']:.1f}%\n\n"
            f"⭐ *Best Day*\n"
            f"Ratio: {status['best_day_ratio']:.0f}% (limit 50%)\n\n"
            f"📊 *Stats*\n"
            f"Trading Days: {status['trading_days']}\n"
            f"Today Trades: {status['today_trades']}\n"
            f"API Requests: {status['today_requests']}/2000\n"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def _cmd_kill(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Emergency kill switch."""
        if self.guardian:
            self.guardian.activate_kill_switch("Manual /kill command")
            await update.message.reply_text(
                "🚨 *KILL SWITCH ACTIVATED*\n"
                "All trading halted.\n"
                "Close all positions manually or restart bot.",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text("⚠️ Guardian not initialized")

    # ─── Notification Methods ─────────────────────────────────

    async def send_message(self, text: str, parse_mode: str = "Markdown") -> None:
        """Send a message to the configured chat."""
        if not self._app or not self.chat_id:
            logger.debug("Telegram send skipped (not configured): {}", text[:50])
            return

        try:
            await self._app.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=parse_mode,
            )
        except Exception as e:
            logger.error("Telegram send failed: {}", e)

    async def notify_trade_opened(self, trade: dict) -> None:
        """Send trade opened notification."""
        direction_emoji = "🟢" if trade.get("direction") == "BUY" else "🔴"
        msg = (
            f"{direction_emoji} *Trade Opened*\n"
            f"─────────────────\n"
            f"Symbol: {trade.get('symbol')}\n"
            f"Direction: {trade.get('direction')}\n"
            f"Lot: {trade.get('lot_size')}\n"
            f"Entry: {trade.get('entry_price')}\n"
            f"SL: {trade.get('stop_loss')}\n"
            f"TP1: {trade.get('take_profit_1')}\n"
            f"Ticket: {trade.get('ticket')}\n"
        )
        await self.send_message(msg)

    async def notify_trade_closed(self, trade: dict) -> None:
        """Send trade closed notification."""
        pnl = trade.get("pnl", 0)
        emoji = "💰" if pnl > 0 else "💸"
        msg = (
            f"{emoji} *Trade Closed*\n"
            f"─────────────────\n"
            f"Symbol: {trade.get('symbol')}\n"
            f"PnL: ${pnl:+.2f}\n"
            f"Ticket: {trade.get('ticket')}\n"
        )
        await self.send_message(msg)

    async def notify_signal(self, signal: dict) -> None:
        """Send signal-only notification (for manual execution)."""
        direction_emoji = "🟢" if signal.get("direction") == "BUY" else "🔴"
        msg = (
            f"🔔 *Signal (Manual)*\n"
            f"─────────────────\n"
            f"{direction_emoji} {signal.get('direction')} {signal.get('symbol')}\n"
            f"Type: {signal.get('signal_type')}\n"
            f"Entry: {signal.get('entry_price')}\n"
            f"SL: {signal.get('stop_loss')}\n"
            f"TP1: {signal.get('take_profit_1')}\n"
            f"TP2: {signal.get('take_profit_2')}\n"
            f"RR: {signal.get('risk_reward_ratio', 0):.1f}\n"
            f"Session: {signal.get('session')}\n"
        )
        await self.send_message(msg)

    async def notify_trade_blocked(self, reason: str) -> None:
        """Send trade blocked notification."""
        msg = f"🚫 *Trade Blocked*\n{reason}"
        await self.send_message(msg)

    async def notify_error(self, error: str) -> None:
        """Send error notification."""
        msg = f"❌ *Error*\n```\n{str(error)[:500]}\n```"
        await self.send_message(msg)

    async def notify_emergency(self, message: str) -> None:
        """Send emergency notification."""
        msg = f"🚨🚨🚨 *EMERGENCY*\n{message}"
        await self.send_message(msg)
