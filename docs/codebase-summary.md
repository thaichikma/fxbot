# Codebase Summary

FXBot is a **Python 3.11+** modular monolith: MT5 integration, SQLite state, SMC/strategy engines, backtest, and optional ML.

## Directory Structure

| Path | Role |
|------|------|
| `config/` | `settings.yaml`, `symbols.yaml`, `ftmo_rules.yaml` |
| `src/core/` | `mt5_client.py` (Windows), `mt5_mock.py` (non-Windows dev) |
| `src/data/` | `db.py` (async SQLite: trades, signals, daily_pnl, **ohlc_bars**), `mtf_store.py`, `mtf_schema.py`, `mtf_csv_import.py`, models |
| `src/risk/` | `ftmo_guardian.py`, `daily_tracker.py`, `risk_manager.py` |
| `src/strategy/` | `smc_engine.py` (pandas SMC), `h1_m5_engine.py`, `ml_engine.py`, `scanner.py`, session/news filters |
| `src/ml/` | Indicators (RSI, ATR), features, XGBoost/LSTM helpers (optional deps) |
| `src/telegram/` | Telegram bot commands |
| `src/utils/` | Logger, timezone, calculators |
| `backtest/` | Engine, reporter, costs, data loader, MTF simulation helpers, metrics |
| `scripts/` | `mtf_import_csv.py`, `ml_train.py`, `xau_data_info.py`, `ftmo_challenge_sim.py`, etc. |
| `tests/` | pytest (guardian, risk, SMC, scanner, backtest, MTF store, real CSV/DB) |
| `docs/` | Architecture and deployment notes |

## Core Dependencies

- **MetaTrader5** (Windows only, in `requirements.txt`)
- **pandas / numpy** — OHLC and SMC logic (no `smartmoneyconcepts` library in repo)
- **pydantic** & **aiosqlite** — models and async DB
- **loguru**, **python-telegram-bot**, **pyyaml**, **python-dotenv**
- **Optional ML:** `requirements-ml.txt` — `xgboost`, `torch`

## Strategy Note

SMC signals are implemented in **`src/strategy/smc_engine.py`** using pandas (FVG, bias, structure), not a third-party SMC package.
