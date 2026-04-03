# Codebase Summary

The FXBot project utilizes a Modular Monolith architecture built strictly on Python 3.11+. The project leans on heavily decoupling State tracking, Market API hooking, and Strategy computation.

## Directory Structure
- `/config/`: Master settings, symbols mapping, and absolute FTMO invariant rules (`.yaml`).
- `/src/core/`: Interfaces with MT5 environments. Houses `mt5_client.py` for live Windows MT5 and `mt5_mock.py` for synthetic MAC testing.
- `/src/data/`: `aiosqlite` abstraction layers alongside strict Pydantic schemas validating Trade, Signal, and Account states.
- `/src/risk/`: Capital protection layers, critically housing `ftmo_guardian.py` (Rule enforcer) and `daily_tracker.py`.
- `/src/strategy/`: Price action computation parsing dataframes via the `smartmoneyconcepts` library into viable setup signals. Includes time-window session scoping.
- `/src/telegram/`: Telemetry API hook linking bot actions to Telegram slash commands `/status`, `/ftmo`, etc.
- `/src/utils/`: Timezone normalization tools forcing data into UTC/CEST formats alongside mathematically precise position pip/lot calculators.
- `/tests/`: `pytest` suites validating rule boundaries (Currently 100% test coverage on `FTMOGuardian`).
- `/backtest/`: Scaffolding for processing historical dataset validations.

## Core Dependencies
- `MetaTrader5`: Data pulling and command forwarding on Windows instances.
- `smartmoneyconcepts`: Baseline for technical analysis identification (SMC).
- `pydantic` & `aiosqlite`: Data representation and async I/O writing.
- `loguru`: Prettified logging.
- `python-telegram-bot`: Command line telemetry via standard chat interactions.
