"""
Telegram Bot — Command handler and notification system.

Phase 1 shell with basic commands:
/start, /status, /help, /ping

Full command suite implemented in Phase 3.
"""

from __future__ import annotations

import asyncio
import functools
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from loguru import logger

from backtest.run import run_backtest_report

# Telegram message limit; split long backtest output
_TELEGRAM_TEXT_CHUNK = 4000

_BACKTEST_HELP = """📊 Backtest (CSV M15: time,open,high,low,close)

Cách dùng nhanh:
• /backtest — chạy file mặc định trong config (backtest.default_csv)
• /bt — giống /backtest
• /backtest help — bản hướng dẫn này
• /backtest status — xem symbol + đường dẫn CSV mặc định + có file hay không
• /backtest data/backtest/my.csv — 1 đối số = đường dẫn CSV (symbol = default_symbol)
• /backtest XAUUSD data/backtest/xau.csv — symbol + đường dẫn

File CSV phải có thật trên máy chạy bot (copy vào repo, ví dụ data/backtest/xau.csv).
Repo có sẵn: data/backtest/sample_m15.csv. Đường dẫn tương đối từ thư mục gốc (có config/). Dùng / hoặc \\ trên Windows."""

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
    from src.core.trading_state import TradingState
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
        trading_state: Optional["TradingState"] = None,
        order_manager: Any = None,
        session_filter: Any = None,
        news_filter: Any = None,
        settings: Optional[dict] = None,
        project_root: Path | str | None = None,
    ):
        self.token = token
        self.chat_id = chat_id
        self.project_root = Path(project_root).resolve() if project_root else None
        self.guardian = guardian
        self.tracker = tracker
        self.mt5_client = mt5_client
        self.trading_state = trading_state
        self.order_manager = order_manager
        self.session_filter = session_filter
        self.news_filter = news_filter
        self.settings = settings or {}
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
            CommandHandler("unkill", self._cmd_unkill),
            CommandHandler("auto", self._cmd_auto),
            CommandHandler("exec", self._cmd_exec),
            CommandHandler("risk", self._cmd_risk),
            CommandHandler("trades", self._cmd_trades),
            CommandHandler("session", self._cmd_session),
            CommandHandler("config", self._cmd_config),
            CommandHandler("challenge", self._cmd_challenge),
            CommandHandler(["backtest", "bt"], self._cmd_backtest),
        ]
        for handler in handlers:
            self._app.add_handler(handler)
        self._app.add_error_handler(self._on_error)

    async def _on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Log handler exceptions (avoids silent 'No error handlers are registered')."""
        err = context.error
        logger.exception("Telegram handler error: {}", err)

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
            "🔹 /status /ping /config\n"
            "🔹 /ftmo /challenge\n"
            "🔹 /auto on|off — Auto mode (session)\n"
            "🔹 /exec on|off — Allow MT5 orders\n"
            "🔹 /risk [pct] — Risk %% per trade\n"
            "🔹 /trades — Open positions\n"
            "🔹 /session — Session filter\n"
            "🔹 /kill — Kill switch + close all\n"
            "🔹 /unkill — Tắt kill switch (cho phép trade lại nếu /exec + session)\n"
            "🔹 /backtest hoặc /bt — backtest CSV M15 (/backtest help)\n"
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
        """Emergency kill switch + close all positions."""
        if self.guardian:
            self.guardian.activate_kill_switch("Manual /kill command")
        lines = ["🚨 *KILL SWITCH ACTIVATED*", "Trading halted."]
        if self.order_manager:
            msgs = await self.order_manager.close_all_positions()
            if msgs:
                lines.append("Closed: " + "; ".join(msgs[:5]))
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def _cmd_unkill(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Tắt kill switch (không mở lại lệnh tự động — chỉ gỡ chặn Guardian)."""
        if not self.guardian:
            await update.message.reply_text("Guardian not initialized.")
            return
        self.guardian.deactivate_kill_switch()
        await update.message.reply_text(
            "Kill switch: OFF. Bot có thể giao dịch lại nếu "
            "execution_enabled + auto/session cho phép (xem /config)."
        )

    async def _cmd_auto(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Toggle hybrid auto mode (execute when session allows)."""
        if not self.trading_state:
            await update.message.reply_text("⚠️ Trading state not wired")
            return
        args = context.args or []
        if not args:
            await update.message.reply_text(f"auto_mode = `{self.trading_state.auto_mode}`")
            return
        v = args[0].lower()
        if v == "on":
            self.trading_state.auto_mode = True
        elif v == "off":
            self.trading_state.auto_mode = False
        await update.message.reply_text(f"auto_mode = `{self.trading_state.auto_mode}`")

    async def _cmd_exec(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Toggle order execution (master switch)."""
        if not self.trading_state:
            await update.message.reply_text("⚠️ Trading state not wired")
            return
        args = context.args or []
        if not args:
            await update.message.reply_text(f"execution_enabled = `{self.trading_state.execution_enabled}`")
            return
        v = args[0].lower()
        if v == "on":
            self.trading_state.execution_enabled = True
        elif v == "off":
            self.trading_state.execution_enabled = False
        await update.message.reply_text(f"execution_enabled = `{self.trading_state.execution_enabled}`")

    async def _cmd_risk(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Set or show risk per trade (%%)."""
        if not self.trading_state:
            await update.message.reply_text("⚠️ Trading state not wired")
            return
        args = context.args or []
        risk_def = 1.0
        if self.settings.get("risk"):
            risk_def = float(self.settings["risk"].get("risk_per_trade", 0.01)) * 100
        if not args:
            if self.trading_state.risk_per_trade is not None:
                pct = self.trading_state.risk_per_trade * 100
                await update.message.reply_text(f"risk override = `{pct:.2f}%`")
            else:
                await update.message.reply_text(f"risk = `{risk_def:.2f}%` (from settings)")
            return
        try:
            pct = float(args[0])
            self.trading_state.risk_per_trade = pct / 100.0
            await update.message.reply_text(f"risk = `{pct:.2f}%`")
        except ValueError:
            await update.message.reply_text("Usage: /risk 0.5")

    async def _cmd_trades(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """List open MT5 positions."""
        if not self.mt5_client:
            await update.message.reply_text("⚠️ No MT5")
            return
        pos = self.mt5_client.get_positions()
        if not pos:
            await update.message.reply_text("No open positions.")
            return
        lines = ["📊 *Open positions*", "─────────────────"]
        for p in pos[:15]:
            lines.append(
                f"`{p.get('ticket')}` {p.get('symbol')} {p.get('type')} "
                f"{p.get('volume', 0):.2f} | P/L ${p.get('profit', 0):.2f}"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def _cmd_session(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Current session (UTC)."""
        if not self.session_filter:
            await update.message.reply_text("⚠️ Session filter not wired")
            return
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        name = self.session_filter.classify_session(now)
        auto = self.session_filter.auto_trade_allowed(now)
        q = self.session_filter.session_quality(now)
        # HTML: Markdown breaks on underscores in e.g. auto_trade_allowed
        await update.message.reply_text(
            f"Session: <code>{escape(str(name))}</code>\n"
            f"auto_trade_allowed: <code>{auto}</code>\n"
            f"quality: <code>{q:.2f}</code>\n"
            "(UTC now)",
            parse_mode="HTML",
        )

    async def _cmd_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show key runtime flags."""
        sys_ = self.settings.get("system", {})
        lines = [
            "<b>Runtime</b>",
            f"auto_mode (YAML): <code>{escape(str(sys_.get('auto_mode')))}</code>",
            f"execution (YAML): <code>{escape(str(sys_.get('execution_enabled')))}</code>",
        ]
        if self.trading_state:
            lines.extend(
                [
                    f"state.auto: <code>{escape(str(self.trading_state.auto_mode))}</code>",
                    f"state.exec: <code>{escape(str(self.trading_state.execution_enabled))}</code>",
                ]
            )
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def _cmd_challenge(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Challenge progress summary."""
        if not self.guardian or not self.mt5_client or not self.settings:
            await update.message.reply_text("⚠️ Not initialized")
            return
        acc = self.settings.get("account", {})
        eq = self.mt5_client.get_account_info().equity
        st = self.guardian.get_status(eq)
        init = float(acc.get("initial_balance", 10000))
        profit = eq - init
        tgt = init * 0.10 if acc.get("challenge_phase") == "phase1" else init * 0.05
        msg = (
            f"🏆 *Challenge*\n"
            f"Phase: `{acc.get('challenge_phase')}`\n"
            f"Profit: `${profit:+.2f}` / target ~`${tgt:.0f}`\n"
            f"Equity: `${eq:,.2f}`\n"
            f"Opens today: `{st['today_trades']}`\n"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def _reply_text_chunks(self, update: Update, text: str, chunk: int = _TELEGRAM_TEXT_CHUNK) -> None:
        """Send long plain text in multiple messages (Telegram limit 4096)."""
        text = text.strip()
        if not text:
            await update.message.reply_text("(empty)")
            return
        for i in range(0, len(text), chunk):
            await update.message.reply_text(text[i : i + chunk])

    async def _cmd_backtest(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Chạy backtest từ CSV (M15) và gửi báo cáo reporter."""
        root = self.project_root or Path(__file__).resolve().parent.parent.parent
        bt = self.settings.get("backtest", {}) if self.settings else {}
        default_symbol = str(bt.get("default_symbol", "EURUSD")).upper()
        default_balance = float(bt.get("initial_balance", 10_000.0))
        step = int(bt.get("step_bars", 4))
        min_bars = int(bt.get("min_m15_bars", 120))
        csv_default = str(bt.get("default_csv", "") or "").strip()
        default_path = (root / csv_default).resolve() if csv_default else None

        raw_args = context.args or []
        args = [a.strip() for a in raw_args if a.strip()]

        if len(args) >= 1:
            sub = args[0].lower()
            if sub in ("help", "h", "?"):
                await update.message.reply_text(_BACKTEST_HELP)
                return
            if sub == "status":
                exists = default_path.is_file() if default_path else False
                line_path = str(default_path) if default_path else "(chưa set default_csv)"
                await update.message.reply_text(
                    "📊 Backtest (config)\n"
                    f"• default_symbol: {default_symbol}\n"
                    f"• default_csv: {csv_default or '(trống)'}\n"
                    f"• file tồn tại: {'có' if exists else 'không'}\n"
                    f"• đường dẫn đầy đủ:\n{line_path}\n"
                    f"• balance/step/min_bars: {default_balance} / {step} / {min_bars}",
                )
                return

        if len(args) == 0:
            if not csv_default:
                await update.message.reply_text(
                    "Chưa có backtest.default_csv trong settings.yaml.\n\n" + _BACKTEST_HELP,
                )
                return
            symbol = default_symbol
            csv_arg = csv_default
        elif len(args) == 1:
            symbol = default_symbol
            csv_arg = args[0]
        else:
            symbol = args[0].upper()
            csv_arg = " ".join(args[1:])

        status = await update.message.reply_text("⏳ Đang chạy backtest...")

        loop = asyncio.get_running_loop()
        try:
            text = await loop.run_in_executor(
                None,
                functools.partial(
                    run_backtest_report,
                    root,
                    symbol=symbol,
                    csv=csv_arg,
                    balance=default_balance,
                    step_bars=step,
                    min_m15_bars=min_bars,
                ),
            )
        except FileNotFoundError as e:
            try:
                await status.delete()
            except Exception:
                pass
            await update.message.reply_text(
                "Không thấy file CSV trên máy chủ bot.\n\n"
                "• Copy file M15 vào thư mục project, ví dụ: data/backtest/xau.csv\n"
                "• Hoặc dùng file mẫu: data/backtest/sample_m15.csv\n"
                "• Hoặc /backtest (không tham số) nếu default_csv trong settings trỏ đúng file có sẵn\n\n"
                f"{e}\n\n/backtest help"
            )
            return
        except Exception as e:
            logger.exception("Telegram /backtest failed")
            err = str(e)[:3500]
            try:
                await status.delete()
            except Exception:
                pass
            await update.message.reply_text(f"Backtest lỗi:\n{err}")
            return

        try:
            await status.delete()
        except Exception:
            pass

        await self._reply_text_chunks(update, text)

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
