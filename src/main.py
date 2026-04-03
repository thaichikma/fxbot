"""
FXBot — MT5 Trading System for FTMO

Main entry point. Initializes all components and runs the trading loop.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv
from loguru import logger

from src.utils.logger import setup_logger
from src.core.order_manager import OrderManager
from src.core.trading_state import TradingState
from src.data.db import Database
from src.risk.daily_tracker import DailyTracker
from src.risk.ftmo_guardian import FTMOGuardian, GuardianConfig
from src.risk.risk_manager import RiskManager
from src.strategy.news_filter import NewsFilter
from src.strategy.h1_m5_engine import H1M5Engine
from src.strategy.ml_engine import MLEngine
from src.strategy.scanner import SignalScanner
from src.strategy.session_filter import SessionFilter
from src.strategy.smc_engine import SMCEngine

# Detect platform for MT5 client
IS_WINDOWS = sys.platform == "win32"

ROOT = Path(__file__).resolve().parent.parent


def load_config(path: str = "config/settings.yaml") -> dict:
    """Load settings YAML config."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_ftmo_rules(path: str = "config/ftmo_rules.yaml") -> dict:
    """Load FTMO rules YAML config."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_symbols(path: Path | None = None) -> dict:
    """Load symbol specs (pip size, contract) for SMC / risk."""
    p = path or ROOT / "config" / "symbols.yaml"
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def create_guardian_config(ftmo_rules: dict, settings: dict) -> GuardianConfig:
    """Build GuardianConfig from YAML files."""
    challenge_type = settings.get("account", {}).get("challenge_type", "2-step")
    phase = settings.get("account", {}).get("challenge_phase", "phase1")

    # Get phase-specific rules
    challenge_key = "two_step" if challenge_type == "2-step" else "one_step"
    phase_rules = ftmo_rules.get("challenges", {}).get(challenge_key, {}).get(phase, {})
    buffers = ftmo_rules.get("safety_buffers", {})
    risk_settings = settings.get("risk", {})

    return GuardianConfig(
        max_daily_loss_pct=phase_rules.get("max_daily_loss_pct", 0.05),
        max_overall_loss_pct=phase_rules.get("max_overall_loss_pct", 0.10),
        max_single_day_profit_pct=ftmo_rules.get("best_day", {}).get("max_pct_of_total_profit", 0.50),
        daily_loss_trigger_pct=buffers.get("daily_loss_trigger_pct", 0.80),
        overall_loss_trigger_pct=buffers.get("overall_loss_trigger_pct", 0.90),
        best_day_cap_pct=buffers.get("best_day_cap_pct", 0.40),
        hyperactivity_buffer=buffers.get("hyperactivity_buffer", 200),
        max_requests_per_day=ftmo_rules.get("hyperactivity", {}).get("max_requests_per_day", 2000),
        max_open_orders=ftmo_rules.get("hyperactivity", {}).get("max_open_orders", 200),
        max_concurrent_trades=risk_settings.get("max_concurrent_trades", 3),
        max_daily_trades=risk_settings.get("max_daily_trades", 8),
    )


async def main():
    """Main application entry point."""
    # Load environment
    load_dotenv()

    # Load configs
    settings = load_config()
    ftmo_rules = load_ftmo_rules()
    symbols_yaml = load_symbols()
    symbols_specs = symbols_yaml.get("symbols", {})

    # Setup logging
    system_cfg = settings.get("system", {})
    setup_logger(
        log_level=system_cfg.get("log_level", "INFO"),
        log_dir=system_cfg.get("log_dir", "logs"),
    )

    logger.info("=" * 50)
    logger.info("FXBot MT5/FTMO Starting...")
    logger.info("=" * 50)

    # Initialize database
    db = Database(system_cfg.get("db_path", "data/fxbot.db"))
    await db.initialize()

    # Initialize MT5 client
    if IS_WINDOWS:
        from src.core.mt5_client import MT5Client
        mt5_cfg = settings.get("mt5", {})
        mt5_client = MT5Client(
            login=int(os.getenv("MT5_LOGIN", "0")),
            password=os.getenv("MT5_PASSWORD", ""),
            server=os.getenv("MT5_SERVER", ""),
            path=os.getenv("MT5_PATH", ""),
            magic_number=mt5_cfg.get("magic_number", 20260403),
            deviation=mt5_cfg.get("deviation", 20),
            filling_type=mt5_cfg.get("filling_type", "ioc"),
        )
        if not mt5_client.initialize():
            logger.critical("Failed to connect to MT5 — exiting")
            return
    else:
        from src.core.mt5_mock import MT5Mock
        initial_balance = settings.get("account", {}).get("initial_balance", 10000)
        mt5_client = MT5Mock(initial_balance=initial_balance)
        mt5_client.initialize()
        logger.warning("Running with MT5Mock (non-Windows platform)")

    # Get account info
    account = mt5_client.get_account_info()
    initial_balance = settings.get("account", {}).get("initial_balance", account.balance)
    logger.info("Account: balance={} equity={} server={}", account.balance, account.equity, account.server)

    # Initialize risk modules
    daily_tracker = DailyTracker(starting_balance=initial_balance)

    # Load historical daily PnL
    all_daily = await db.get_all_daily_pnl()
    daily_tracker.load_history(all_daily)

    guardian_config = create_guardian_config(ftmo_rules, settings)
    guardian = FTMOGuardian(
        config=guardian_config,
        tracker=daily_tracker,
        initial_balance=initial_balance,
    )

    # Phase 2 — strategy stack (scan + notify only; no orders)
    strategy_merged = dict(settings.get("strategy", {}))
    strategy_merged["max_signals_per_scan_per_symbol"] = system_cfg.get(
        "max_signals_per_scan_per_symbol", 2
    )
    session_filter = SessionFilter(settings.get("sessions", {}))
    news_filter = NewsFilter(settings.get("news", {}))
    smc_engine = SMCEngine(strategy_merged, symbols_specs)
    h1_m5_engine = H1M5Engine(strategy_merged, symbols_specs)
    ml_engine = MLEngine(settings, symbols_specs)
    signal_scanner = SignalScanner(
        settings,
        symbols_specs,
        session_filter,
        news_filter,
        smc_engine,
        h1_m5_engine=h1_m5_engine,
        ml_engine=ml_engine,
    )

    trading_state = TradingState.from_settings(system_cfg)
    risk_manager = RiskManager(settings, symbols_specs, symbols_yaml)
    order_manager = OrderManager(
        mt5_client,
        guardian,
        risk_manager,
        db,
        daily_tracker,
        settings,
    )

    # Initialize Telegram bot
    telegram_cfg = settings.get("telegram", {})
    if telegram_cfg.get("enabled", True):
        from src.telegram.bot import TelegramBot
        telegram = TelegramBot(
            token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            guardian=guardian,
            tracker=daily_tracker,
            mt5_client=mt5_client,
            trading_state=trading_state,
            order_manager=order_manager,
            session_filter=session_filter,
            news_filter=news_filter,
            settings=settings,
            project_root=ROOT,
        )
        await telegram.start()
        await telegram.send_message("🚀 *FXBot Started*\nSystem online and ready.")
    else:
        telegram = None

    # Main trading loop
    scan_interval = system_cfg.get("scan_interval_seconds", 15)
    logger.info("Starting main loop | interval={}s", scan_interval)

    try:
        while True:
            try:
                # 1. Update account info
                account = mt5_client.get_account_info()
                daily_tracker.update_equity(account.equity)
                daily_tracker.sync_requests(getattr(mt5_client, "request_count", 0))

                now = datetime.now(timezone.utc)

                # 2. Monitor equity (FTMO Guardian)
                safe, emergency_msg = guardian.monitor_equity(account.equity)
                if not safe:
                    logger.critical(emergency_msg)
                    if telegram:
                        await telegram.notify_emergency(emergency_msg)
                    # TODO: Emergency close all positions
                    guardian.activate_kill_switch(emergency_msg)

                # 3. Daily reset check
                if daily_tracker.check_reset():
                    daily_tracker.update_balance(account.balance)
                    logger.info("Daily reset | new starting balance={}", account.balance)

                # 4. Manage open trades (partial TP / breakeven)
                await order_manager.manage_open_trades()

                # 5. Signal scan + hybrid execution
                if system_cfg.get("signal_scan_enabled", True):
                    signals = await signal_scanner.scan(mt5_client, db)
                    default_risk = float(settings.get("risk", {}).get("risk_per_trade", 0.01))
                    risk_pct = trading_state.effective_risk_pct(default_risk)

                    exec_ok = (
                        trading_state.execution_enabled
                        and trading_state.auto_mode
                        and session_filter.auto_trade_allowed(now)
                        and not guardian.kill_switch_active
                    )

                    for sig in signals:
                        if exec_ok:
                            trade = await order_manager.execute_signal(sig, risk_pct)
                            if trade and telegram:
                                await telegram.notify_trade_opened(trade)
                        elif telegram:
                            await telegram.notify_signal(sig.model_dump(mode="json"))

                # Save daily snapshot to DB
                snapshot = daily_tracker._get_today_snapshot()
                snapshot["max_equity"] = max(snapshot.get("max_equity", 0), account.equity)
                snapshot["min_equity"] = min(snapshot.get("min_equity", float('inf')), account.equity)
                await db.upsert_daily_pnl(snapshot)

            except Exception as e:
                logger.error("Main loop error: {}", e)
                if telegram:
                    await telegram.notify_error(str(e))

            await asyncio.sleep(scan_interval)

    except KeyboardInterrupt:
        logger.info("Shutdown requested...")
    finally:
        # Cleanup
        if telegram:
            await telegram.send_message("⛔ *FXBot Shutting Down*")
            await telegram.stop()
        mt5_client.shutdown()
        await db.close()
        logger.info("FXBot stopped")


if __name__ == "__main__":
    asyncio.run(main())
