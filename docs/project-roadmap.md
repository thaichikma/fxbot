# Project Roadmap

The immediate goal focuses on generating a reliable trading bot structure adhering inherently strictly to simulated constraints before transitioning to pure AI-based quality filtering evaluations. 

## Phase 1: Foundation (Completed ✓)
- Base Architecture scaffolding
- MT5 Connection Proxies (Mac testing and Win deployment bounds)
- Strict FTMO Rule Enforcement Guarding layer 
- Telegram Control Shell and Monitoring Tracking Base

## Phase 2: Strategy Core (Completed)
- SMC engine in pandas (`smc_engine.py` — bias, structure, FVG); optional **H1/M5** and **ML** profiles
- News API + session scheduling; multi-pair scanner (`strategy: smc | h1_m5 | ml`)

## Phase 3: Execution & Risk (Completed)
- Advanced Scaling (Fractional closures triggering SL-Breakeven adjustments)
- Multi-Order management linking tracking hashes to telegram outputs
- Deep Configuration implementations (Correlation mapping and limits)

## Phase 4: Backtesting & Validation (Completed)
- Historical CSV + optional **M1 exit** resolution; costs model; **MTF SQLite** import (`mtf_import_csv.py`)
- Paper checklist + CLI/Telegram backtest; tests on real CSV / DB

## Phase 5: FTMO Demo to Live Sandbox (Completed)
- Windows VPS provisioning và vận hành (xem [`deployment.md`](deployment.md))
- Deploy tới FTMO Demo / Free Trial; xác minh Guardian và MetriX
- Checklist go-live challenge trả phí

## Phase 6/7: ML Signal Quality Evaluation (In progress)
- **Done:** RSI/ATR/volume features (`src/ml/`), `scripts/ml_train.py` (XGBoost / LSTM), `MLEngine` + `settings.ml`
- **Pending:** automated signal extraction from DB for post-labeling; LightGBM / ensemble; explicit quality score 0–100 gating beyond current probability threshold 
