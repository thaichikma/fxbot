# System Architecture

## Architecture Overview
The bot utilizes a **Modular Monolith** driven by an `async` Python loop engine (`src/main.py`), ensuring Non-Blocking executions for continuous Telemetry and File I/O operations while waiting for tick data.

### High-Level Component Flow
1. **Clock & Market Schedule (Tick Loop)**
    - Verifies timezone constraints ensuring execution falls cleanly into active sessions (London/NY overlaps), bypassing news blockages.
2. **Signal Scanning (Strategy Engine)**
    - Multi-timeframe OHLCV dataset requests are sent to the `MT5 Client` and subsequently pushed into the `SMCEngine`.
    - Yields `Signal` Pydantic objects ranking trade quality properties.
3. **FTMO Security Gate (The Guardian)**
    - An intended `Signal` crosses into the `FTMOGuardian` and undergoes 7 structural bounds-checks.
    - Factors evaluated: PnL Buffers (4%), Drawdown Triggers, Best-day proportion violations, MT5 hyperactivity request limits.
4. **Execution Layer (Order Manager)**
    - Determines standard Lot Size sizing bounded to static risk ratios (1% Base).
    - Submits Limit/Market Order back to the MT5 Client with dynamically placed Take Profit milestones.
5. **State Management**
    - Active configurations, Daily Trackers, and PnL updates sink asynchronously into a local SQLite repository.
6. **Telemetry Alerts**
    - Live updates reflect simultaneously back to the linked Telegram client alerting the user securely to operations.
    - Provides a `/kill` switch manual override hook pushing directly to the MT5 closer.

## Error Handling & Resiliency
- `MT5Client` actively reconnects to terminals via an exponential backoff retry.
- All actions inside loops use broad `Exception` catches logged via Loguru `CRITICAL` alerting so continuous tracking never dies due to single-symbol computation faults.
