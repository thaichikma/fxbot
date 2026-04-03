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
- [ ] SMC Engine (BOS/CHoCH, OB, FVG, Liquidity)
- [ ] Session Filter
- [ ] News Filter
- [ ] Signal Scanner (multi-pair)
- [ ] Tests for SMC Engine

## Phase 3: Execution & Risk (Week 5-6)
- [ ] Risk Manager (position sizing, correlation)
- [ ] Order Manager (entry, SL, TP, trailing, breakeven)
- [ ] Hybrid mode logic
- [ ] Telegram commands full suite
- [ ] Main loop (main.py)
- [ ] Integration tests

## Phase 4: Backtesting & Validation (Week 7-8)
- [ ] Backtest engine
- [ ] Performance reporter
- [ ] FTMO challenge simulation
- [ ] Paper trading validation

## Phase 5: Deployment (Week 9+)
- [ ] Windows VPS setup
- [ ] FTMO Free Trial testing
- [ ] Go live

## Phase 6: ML/AI Layer (Month 3-4)
- [ ] Data collection pipeline
- [ ] Feature engineering
- [ ] Model training
- [ ] A/B testing
