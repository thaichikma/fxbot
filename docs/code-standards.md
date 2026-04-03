# Code Standards & Guidelines

FXBot adheres to standards minimizing ambiguity specifically focusing on defensive risk practices, readability, type safety, and pure asynchronous Python patterns. 

## Python Ecosystem
- **Typing**: Strict type hinting (`mypy`) is mandated for all function signatures. Types imported generally from `typing` natively.
- **Pydantic**: Any complex data shapes (Signals, Trades, APIs) MUST be validated through Pydantic `BaseModel` classes before being processed down logic streams.
- **Async First**: Code interacting via generic HTTP APIs and SQLite processing uses `async/await` to unblock threads. Local mathematical heuristics generally run synchronously natively.
- **Linting**: Enforcement configured against `ruff` matching widely accepted PEP-8 implementations.

## Trading Bot Specific Principles
1. **Never Bypass Guardian**:
   Any execution commands aiming toward MT5 *must* be funneled sequentially through the `FTMOGuardian` pipeline. Circumventing the module risks automatic challenge failures. 
2. **Immutable Variables**:
   Constants impacting absolute limits specifically contained in `ftmo_rules.yaml` should NOT be adjustable variables.
3. **Decimals Over Floats**
   Critical calculation rounding relating directly to Balance calculations and Margin requirements rely rigorously on precision calculation math avoiding localized float drifting.
4. **Log Levels Matter**:
    - `INFO`: Basic milestone entries (bot start, signal caught, daily reset).
    - `DEBUG`: Heavy volume items stored only in local logs (Lot math calculations, tick price streaming).
    - `CRITICAL`/`ERROR`: Broad exceptions or Emergency limit threshold overrides (These inherently force Telegram push notifications.)

## Unit Testing
- Components responsible for executing Capital Risk (such as Guardian bounds calculations) must maintain rigorous `pytest` assertion mappings meeting 100% test coverage before Deployment.
