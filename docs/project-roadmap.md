# Project Roadmap

The immediate goal focuses on generating a reliable trading bot structure adhering inherently strictly to simulated constraints before transitioning to pure AI-based quality filtering evaluations. 

## Phase 1: Foundation (Completed ✓)
- Base Architecture scaffolding
- MT5 Connection Proxies (Mac testing and Win deployment bounds)
- Strict FTMO Rule Enforcement Guarding layer 
- Telegram Control Shell and Monitoring Tracking Base

## Phase 2: Strategy Core (Completed)
- Implementing `smartmoneyconcepts` library mapping
- Market structural tracking (Bos, CHoCH, Fair value gaps, Order block recognition)
- Implementing News Api and Time/Session scheduling 
- Broad Signal filtering Scanner implementations

## Phase 3: Execution & Risk (Completed)
- Advanced Scaling (Fractional closures triggering SL-Breakeven adjustments)
- Multi-Order management linking tracking hashes to telegram outputs
- Deep Configuration implementations (Correlation mapping and limits)

## Phase 4: Backtesting & Validation (Completed)
- Simulating raw historical data processing 
- Comprehensive paper environment runs simulating 1:1 true limit Challenge configurations

## Phase 5: FTMO Demo to Live Sandbox (Completed)
- Windows VPS provisioning và vận hành (xem [`deployment.md`](deployment.md))
- Deploy tới FTMO Demo / Free Trial; xác minh Guardian và MetriX
- Checklist go-live challenge trả phí

## Phase 6/7: ML Signal Quality Evaluation Pipeline (Pending)
- Extracting historical signals out of SQLite tracking and processing post-event profitability analysis.
- Feature mapping correlations of standard SMC events vs broader market momentum matrices.
- Processing XGBoost / LightGBMs models to output a `Quality 0-100% rating`. 
- Gating active configurations to strictly accept higher modeled setups above generic bounds metrics bounds thresholds. 
