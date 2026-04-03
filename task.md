# FXBot MT5/FTMO — Task Tracker

## Phase 1: Foundation (Week 1-2)

- [x] Project structure & requirements.txt
- [x] Config system (settings.yaml, ftmo_rules.yaml, symbols.yaml)
- [x] Utility modules (logger, timezone, calculations)
- [x] Data models & SQLite database (db.py, models.py)
- [x] MT5 client (mt5_client.py)
- [x] MT5 mock for Mac dev (mt5_mock.py)
- [x] State manager (via data/db.py)
- [x] Basic Telegram bot shell
- [x] FTMO Guardian module
- [x] Daily tracker module
- [x] Tests for FTMO Guardian (100% coverage)

## Phase 2: Strategy Core (Week 3-4)

> Kế hoạch chi tiết (thứ tự, DoD, test): [`plans/260403-fxbot-phase2-strategy/plan.md`](plans/260403-fxbot-phase2-strategy/plan.md)

- [x] SMC Engine (FVG + bias; pandas — không dùng smartmoneyconcepts)
- [x] Session Filter
- [x] News Filter (Finnhub + cache)
- [x] Signal Scanner (multi-pair; profiles `smc` / `h1_m5` / `ml`)
- [x] H1M5Engine, MLEngine + wiring `main.py`
- [x] Tests (session, news, smc, scanner) + main wiring (notify only)

## Phase 3: Execution & Risk (Week 5-6)
- [x] Risk Manager (`risk_manager.py` — sizing + USD basket correlation)
- [x] Order Manager (`order_manager.py` — market entry, partial TP, BE)
- [x] Hybrid mode (`TradingState` + `session_filter.auto_trade` + `execution_enabled`)
- [x] Telegram: `/auto`, `/exec`, `/risk`, `/trades`, `/session`, `/config`, `/challenge` + kill closes positions
- [x] Main loop: `manage_open_trades` → scan → execute or signal-only
- [x] Tests: `test_risk_manager.py` + guardian fix (`_opens_today`)

## Phase 4: Backtesting & Validation (Week 7-8)
- [x] Backtest engine (`backtest/engine.py` — walk-forward M15, SMC, fill model; optional M1 exit)
- [x] Performance reporter (`backtest/reporter.py`)
- [x] FTMO metrics + challenge hints (`backtest/ftmo_challenge.py`)
- [x] Paper trading checklist (`backtest/paper.py`) + CLI `python -m backtest --csv ...`
- [x] SQLite `ohlc_bars` + `MTFOHLCStore` + `scripts/mtf_import_csv.py` (CSV XAU → DB)
- [x] Tests trên CSV thật / DB (`tests/test_real_data_csv.py`, `test_real_data_from_db.py`)

## Phase 5: Deployment (Week 9+)
- [x] Windows VPS setup (hướng dẫn + script PowerShell: `docs/deployment.md`, `scripts/windows/`)
- [x] FTMO Free Trial testing (checklist trong `docs/deployment.md` §6)
- [x] Go live (checklist §7; thực hiện thủ công trên tài khoản FTMO)

## Phase 6: ML/AI Layer (Month 3-4)
- [x] Feature engineering (RSI, ATR, volume — `src/ml/features.py`, `indicators.py`)
- [x] Model training scripts (XGBoost / LSTM — `scripts/ml_train.py`, `requirements-ml.txt`)
- [x] `MLEngine` + pair `strategy: ml` + `settings.ml` (model path, threshold)
- [ ] Data collection pipeline (tự động từ MT5 → DB theo lịch)
- [ ] A/B testing / live shadow mode
