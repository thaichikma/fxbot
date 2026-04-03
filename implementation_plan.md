# FXBot MT5/FTMO — Implementation Plan

## Goal

Build hệ thống giao dịch tự động trên MT5 cho FTMO prop firm challenge ($10K, 2-Step, Swing). Strategy: SMC + Session Filter. Tech: Python + Windows VPS. Risk: 1%/trade. Control: Telegram Bot. Roadmap: ML/AI signal scoring (Phase 2).

---

## User Review Required

> [!IMPORTANT]
> **Windows VPS**: Cần setup Windows VPS ($5-10/mo) trước khi bắt đầu Phase 4 (deployment). Recommend Contabo hoặc Hetzner.

> [!IMPORTANT]
> **FTMO Account**: Cần đăng ký FTMO Free Trial (demo) trước Phase 4 để test integration.

> [!WARNING]
> **Development trên Mac**: `MetaTrader5` Python package chỉ chạy trên Windows. Trong Phase 1-3 ta build code với mock/stub MT5 client, test logic thuần. Phase 4 mới deploy lên Windows VPS để test thực với MT5.

---

## Proposed Changes

### Project Structure

```
fxbot/
├── config/
│   ├── settings.yaml              # Main config (pairs, sessions, risk params)
│   ├── ftmo_rules.yaml            # FTMO hard limits (immutable)
│   └── symbols.yaml               # Symbol-specific config (contract size, spread)
├── src/
│   ├── __init__.py
│   ├── main.py                    # Entry point, async main loop
│   ├── core/
│   │   ├── __init__.py
│   │   ├── mt5_client.py          # MT5 connection, data fetching, account info
│   │   ├── mt5_mock.py            # Mock client for Mac development
│   │   ├── order_manager.py       # Order execution, modification, trailing SL
│   │   └── state_manager.py       # Trade state persistence & recovery
│   ├── strategy/
│   │   ├── __init__.py
│   │   ├── base.py                # Abstract strategy interface
│   │   ├── smc_engine.py          # SMC: swing points, BOS/CHoCH, OB, FVG, Liquidity
│   │   ├── session_filter.py      # London/NY session + overlap detection
│   │   ├── news_filter.py         # Economic calendar fetch & filter
│   │   └── signal_types.py        # Signal/Setup dataclass definitions
│   ├── risk/
│   │   ├── __init__.py
│   │   ├── ftmo_guardian.py       # FTMO rule enforcement (safety valve)
│   │   ├── risk_manager.py        # Position sizing, correlation, exposure
│   │   └── daily_tracker.py       # Daily PnL, best day tracker, trading days counter
│   ├── telegram/
│   │   ├── __init__.py
│   │   ├── bot.py                 # Telegram bot setup & handler registration
│   │   ├── commands.py            # Command handlers (/status, /risk, /auto, etc.)
│   │   └── notifications.py      # Alert formatting & sending
│   ├── data/
│   │   ├── __init__.py
│   │   ├── db.py                  # SQLite connection & migrations
│   │   └── models.py             # Trade, Signal, DailyPnL, Config models
│   └── utils/
│       ├── __init__.py
│       ├── logger.py              # Loguru setup
│       ├── timezone.py            # Session timezone helpers
│       └── calculations.py        # Lot size, pip value, point value helpers
├── backtest/
│   ├── __init__.py
│   ├── engine.py                  # Backtest engine with historical data
│   ├── data_loader.py            # Load MT5 historical data / CSV
│   └── reporter.py               # Performance metrics & equity curve
├── tests/
│   ├── __init__.py
│   ├── test_ftmo_guardian.py      # 100% coverage required
│   ├── test_risk_manager.py
│   ├── test_smc_engine.py
│   ├── test_session_filter.py
│   ├── test_order_manager.py
│   └── test_daily_tracker.py
├── docs/
│   └── brainstorm_mt5_ftmo.md
├── requirements.txt
├── requirements-dev.txt
├── .env.example
├── .gitignore
└── README.md
```

---

### Phase 1: Foundation (Week 1-2)

Core infrastructure: config, database, MT5 client, logging, Telegram shell.

---

#### [NEW] config/settings.yaml

Main configuration file — tất cả runtime settings.

```yaml
# Account
account:
  broker: "FTMO"
  account_type: "swing"        # normal | swing
  challenge_type: "2-step"     # 1-step | 2-step
  initial_balance: 10000
  currency: "USD"

# Trading pairs
pairs:
  - symbol: "XAUUSD"
    enabled: true
    timeframes:
      structure: "H1"         # Market structure analysis
      entry: "M15"            # Entry timing
      bias: "H4"              # Direction bias
    max_spread_points: 50     # Max acceptable spread
    
  - symbol: "EURUSD"
    enabled: true
    timeframes:
      structure: "H1"
      entry: "M15"
      bias: "H4"
    max_spread_points: 20

  - symbol: "GBPUSD"
    enabled: true
    timeframes:
      structure: "H1"
      entry: "M15"
      bias: "H4"
    max_spread_points: 25

  - symbol: "USDJPY"
    enabled: true
    timeframes:
      structure: "H1"
      entry: "M15"
      bias: "H4"
    max_spread_points: 20

# Risk management
risk:
  risk_per_trade: 0.01         # 1% per trade
  max_concurrent_trades: 3     # Max open positions
  max_daily_trades: 8          # Limit trades per day
  max_correlation_trades: 2    # Max same-direction USD pairs
  
# Sessions (UTC+7 Vietnam time for reference, stored as UTC)
sessions:
  london:
    start: "07:00"             # UTC (14:00 VN)
    end: "16:00"               # UTC (23:00 VN)
    auto_trade: true
  new_york:
    start: "12:30"             # UTC (19:30 VN)
    end: "21:00"               # UTC (04:00 VN next day)
    auto_trade: true
  overlap:                     # London-NY overlap = prime time
    start: "12:30"             # UTC
    end: "16:00"               # UTC
    auto_trade: true
  asian:
    start: "23:00"             # UTC
    end: "07:00"               # UTC
    auto_trade: false          # Signal only

# Strategy params
strategy:
  swing_length: 10             # Candles for swing point detection
  ob_lookback: 20              # Order block lookback
  fvg_min_size_pips: 5         # Min FVG size to be valid
  sl_buffer_pips: 5            # Buffer above/below OB for SL
  tp_ratios: [1.5, 2.0, 3.0]  # RR ratios for multi-TP
  tp_portions: [0.5, 0.3, 0.2] # Close 50% at TP1, 30% TP2, 20% TP3
  breakeven_at_tp1: true       # Move SL to entry after TP1
  trailing_after_tp2: true     # Enable trailing after TP2

# Telegram
telegram:
  bot_token: "${TELEGRAM_BOT_TOKEN}"
  chat_id: "${TELEGRAM_CHAT_ID}"
  
# MT5
mt5:
  login: "${MT5_LOGIN}"
  password: "${MT5_PASSWORD}"
  server: "${MT5_SERVER}"
  path: "${MT5_PATH}"          # Path to terminal64.exe
  magic_number: 20260403       # Unique EA identifier
  deviation: 20                # Max slippage in points

# System
system:
  scan_interval_seconds: 15    # Main loop interval
  db_path: "data/fxbot.db"
  log_level: "INFO"
  log_file: "logs/fxbot.log"
```

---

#### [NEW] config/ftmo_rules.yaml

FTMO hard limits — **KHÔNG BAO GIỜ thay đổi bởi user**. Chỉ hệ thống đọc.

```yaml
# FTMO Rules - IMMUTABLE
# These values are absolute limits that cannot be overridden

two_step:
  phase1:
    profit_target_pct: 0.10      # 10%
    max_daily_loss_pct: 0.05     # 5%
    max_overall_loss_pct: 0.10   # 10%
    min_trading_days: 4
  phase2:
    profit_target_pct: 0.05      # 5%
    max_daily_loss_pct: 0.05     # 5%
    max_overall_loss_pct: 0.10   # 10%
    min_trading_days: 4
  funded:
    max_daily_loss_pct: 0.05     # 5%
    max_overall_loss_pct: 0.10   # 10%

# Safety buffers (trigger BEFORE hitting actual limits)
safety_buffers:
  daily_loss_buffer_pct: 0.20    # Trigger at 80% of limit ($400 of $500)
  overall_loss_buffer_pct: 0.10  # Trigger at 90% of limit ($9,100 equity)
  best_day_max_pct: 0.40         # Cap best day at 40% (rule is 50%)
  hyperactivity_buffer: 200      # Stop at 1800 (limit is 2000)

# Best day rule
best_day:
  max_single_day_profit_pct: 0.50  # Best day < 50% of total profit

# Hyperactivity
hyperactivity:
  max_requests_per_day: 2000
  max_open_orders: 200

# Inactivity
inactivity:
  max_days_without_trade: 30
```

---

#### [NEW] src/core/mt5_client.py

MT5 connection wrapper. Handles init, reconnect, data fetching, account info.

```
Key methods:
- initialize() → bool
- shutdown()
- get_account_info() → AccountInfo dataclass
- get_symbol_info(symbol) → SymbolInfo dataclass  
- get_rates(symbol, timeframe, count) → pd.DataFrame
- get_tick(symbol) → Tick dataclass
- get_positions(magic?) → list[Position]
- get_orders(magic?) → list[Order]
- order_send(request) → OrderResult
- position_close(ticket) → OrderResult
- position_modify(ticket, sl, tp) → OrderResult
```

Implementation notes:
- Wrap `MetaTrader5` package calls with retry logic (3 retries, exponential backoff)
- Auto-reconnect on connection loss
- Log every API call for debugging
- Track request count per day (for hyperactivity limit)

---

#### [NEW] src/core/mt5_mock.py

Mock MT5 client for development on Mac. Same interface as `mt5_client.py`.

```
- Returns synthetic OHLCV data (random walk or loaded from CSV)
- Simulates order execution (instant fill, configurable slippage)
- Tracks virtual account balance, equity, positions
- Allows injecting test scenarios (news spike, disconnect, etc.)
```

---

#### [NEW] src/data/db.py & models.py

SQLite database for trade logging, state persistence, daily PnL tracking.

```
Tables:
- trades: id, ticket, symbol, direction, lot_size, entry_price, sl, tp, 
          open_time, close_time, close_price, pnl, status, signal_id
- signals: id, symbol, direction, type (OB/FVG/Liquidity), timeframe,
           entry_zone_high, entry_zone_low, sl, tp1, tp2, tp3, 
           confidence, session, created_at, status (pending/triggered/expired)
- daily_pnl: date, starting_balance, ending_balance, realized_pnl, 
             unrealized_pnl, max_equity, min_equity, trade_count, 
             request_count
- config_state: key, value, updated_at  (for runtime state persistence)
```

---

#### [NEW] src/telegram/bot.py (Shell)

Basic Telegram bot setup with command registration.

```
Commands (Phase 1 shell — full implementation in Phase 3):
/start        - Welcome message + status
/status       - Account balance, equity, open positions, daily PnL
/help         - List all commands
```

---

#### [NEW] src/utils/logger.py

Loguru-based structured logging.

```
- Console output (colorized, INFO level)
- File output (DEBUG level, rotation 10MB, retention 30 days)
- Telegram alert on CRITICAL errors
- Format: timestamp | level | module | message
```

---

### Phase 2: Strategy Core (Week 3-4)

SMC engine, session filter, news filter, signal scanner.

---

#### [NEW] src/strategy/smc_engine.py

Core SMC analysis. Leverages `smartmoneyconcepts` library + custom logic.

```python
# Key components:

class SMCEngine:
    def __init__(self, config):
        self.swing_length = config.strategy.swing_length
        
    def analyze(self, symbol: str, data: dict[str, pd.DataFrame]) -> list[Signal]:
        """
        Analyze multi-timeframe data for SMC setups.
        
        Args:
            symbol: e.g. "XAUUSD"
            data: {"H4": df, "H1": df, "M15": df}
        
        Returns: list of Signal objects
        """
        # Step 1: H4 bias (Supply/Demand zones → bullish/bearish bias)
        bias = self._get_bias(data["H4"])
        
        # Step 2: H1 structure (BOS/CHoCH detection)
        structure = self._analyze_structure(data["H1"])
        
        # Step 3: H1 key levels (Order Blocks, Liquidity pools)
        key_levels = self._find_key_levels(data["H1"], structure)
        
        # Step 4: M15 entry (FVG, OB pullback refinement)
        entries = self._find_entries(data["M15"], bias, structure, key_levels)
        
        return entries

    def _get_bias(self, h4_data) -> str:
        """Determine bullish/bearish bias from H4 structure"""
        swing_hl = smc.swing_highs_lows(h4_data, self.swing_length)
        bos_choch = smc.bos_choch(h4_data, swing_hl)
        # Last BOS direction = current bias
        ...

    def _analyze_structure(self, h1_data) -> MarketStructure:
        """Detect BOS, CHoCH, current trend on H1"""
        swing_hl = smc.swing_highs_lows(h1_data, self.swing_length)
        bos_choch = smc.bos_choch(h1_data, swing_hl, close_break=True)
        ...

    def _find_key_levels(self, h1_data, structure) -> list[KeyLevel]:
        """Find Order Blocks, Liquidity pools, Supply/Demand zones"""
        ob = smc.ob(h1_data, swing_hl, close_mitigation=False)
        liquidity = smc.liquidity(h1_data, swing_hl)
        ...

    def _find_entries(self, m15_data, bias, structure, key_levels) -> list[Signal]:
        """Find specific entry signals on M15"""
        fvg = smc.fvg(m15_data)
        # Match FVG/OB pullback with H1 key levels
        # Generate Signal with entry, SL, TP1/TP2/TP3
        ...
```

**Signal Types:**
1. **OB Pullback** — Price returns to H1 Order Block, M15 shows rejection
2. **FVG Fill** — Price fills M15 FVG at a key level, continues trend
3. **Liquidity Sweep** — Price sweeps H1 liquidity, reverses (CHoCH on M15)
4. **BOS Continuation** — H1 BOS confirmed, M15 pullback to OB/FVG for entry

---

#### [NEW] src/strategy/session_filter.py

```python
class SessionFilter:
    """Filter signals based on trading session"""
    
    def is_trading_session(self, utc_now: datetime) -> tuple[bool, str]:
        """
        Returns (is_active, session_name)
        Sessions: london, new_york, overlap, asian
        """
        ...
    
    def get_auto_trade_allowed(self, utc_now: datetime) -> bool:
        """True if current session allows auto execution"""
        ...
    
    def get_session_quality(self, utc_now: datetime) -> float:
        """
        Score 0-1 for current session quality
        Overlap = 1.0, London/NY = 0.8, Asian = 0.3
        """
        ...
```

---

#### [NEW] src/strategy/news_filter.py

```python
class NewsFilter:
    """Fetch economic calendar and filter around high-impact news"""
    
    BLOCK_BEFORE_HIGH = timedelta(minutes=15)
    BLOCK_AFTER_HIGH = timedelta(minutes=15)
    BLOCK_BEFORE_CRITICAL = timedelta(minutes=30)  # FOMC, NFP, CPI
    BLOCK_AFTER_CRITICAL = timedelta(minutes=30)
    
    def __init__(self):
        self.calendar = []      # Cached daily calendar
        self.last_fetch = None
    
    async def fetch_calendar(self) -> list[NewsEvent]:
        """Fetch today's economic calendar from Finnhub or similar API"""
        ...
    
    def is_news_blocked(self, utc_now: datetime, symbol: str) -> tuple[bool, str]:
        """
        Check if trading is blocked due to upcoming/recent news.
        Returns (is_blocked, reason)
        """
        ...
    
    def get_affected_pairs(self, news: NewsEvent) -> list[str]:
        """Map news currency (USD, EUR) to affected pairs"""
        ...
```

Data source options (ranked by reliability):
1. **Finnhub API** (free tier, 60 calls/min) — most reliable
2. **`market-calendar-tool`** package — scraper, may break
3. **Manual CSV** fallback — download weekly from ForexFactory

---

#### [NEW] src/strategy/signal_types.py

```python
@dataclass
class Signal:
    id: str                    # UUID
    symbol: str                # "XAUUSD"
    direction: str             # "BUY" | "SELL"
    signal_type: str           # "OB_PULLBACK" | "FVG_FILL" | "LIQUIDITY_SWEEP" | "BOS_CONTINUATION"
    
    # Levels
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    
    # Context
    h4_bias: str               # "BULLISH" | "BEARISH"
    h1_structure: str          # "BOS" | "CHOCH"
    session: str               # "london" | "new_york" | "overlap"
    
    # Risk
    sl_distance_pips: float
    risk_reward_ratio: float   # TP1 RR
    
    # Meta
    timeframe: str             # Entry timeframe
    confidence: float          # 0-100 (for future ML scoring)
    created_at: datetime
    status: str                # "pending" | "triggered" | "expired" | "cancelled"
    expiry: datetime           # Signal expires if not triggered
```

---

### Phase 3: Execution & Risk (Week 5-6)

Risk management, order execution, FTMO guardian, hybrid mode, Telegram full suite.

---

#### [NEW] src/risk/ftmo_guardian.py

**Most critical module. Must have 100% test coverage.**

```python
class FTMOGuardian:
    """
    Safety valve - enforces ALL FTMO rules.
    Every order MUST pass through this before execution.
    """
    
    def __init__(self, ftmo_rules, daily_tracker, account_info):
        self.rules = ftmo_rules
        self.tracker = daily_tracker
        self.account = account_info
    
    def can_open_trade(self, signal: Signal, lot_size: float) -> tuple[bool, str]:
        """
        Pre-trade validation. Returns (approved, reason).
        Checks in order of severity:
        """
        checks = [
            self._check_daily_loss,
            self._check_overall_drawdown,
            self._check_best_day_profit,
            self._check_hyperactivity,
            self._check_max_positions,
            self._check_max_daily_trades,
            self._check_spread,
        ]
        for check in checks:
            approved, reason = check(signal, lot_size)
            if not approved:
                return False, reason
        return True, "APPROVED"
    
    def _check_daily_loss(self, signal, lot_size) -> tuple[bool, str]:
        """Block if daily PnL approaching limit"""
        daily_pnl = self.tracker.get_daily_pnl()
        limit = self.account.balance * self.rules.max_daily_loss_pct
        buffer_limit = limit * (1 - self.rules.safety_buffers.daily_loss_buffer_pct)
        
        if daily_pnl <= -buffer_limit:
            return False, f"BLOCKED: Daily loss ${daily_pnl:.2f} near limit ${-limit:.2f}"
        return True, ""
    
    def _check_overall_drawdown(self, signal, lot_size) -> tuple[bool, str]:
        """Block if equity approaching max drawdown"""
        min_equity = self.account.initial_balance * (1 - self.rules.max_overall_loss_pct)
        buffer_equity = min_equity + (self.account.initial_balance * self.rules.safety_buffers.overall_loss_buffer_pct * self.rules.max_overall_loss_pct)
        
        if self.account.equity <= buffer_equity:
            return False, f"BLOCKED: Equity ${self.account.equity:.2f} near limit ${min_equity:.2f}"
        return True, ""
    
    def _check_best_day_profit(self, signal, lot_size) -> tuple[bool, str]:
        """Block if today's profit would violate best day rule"""
        today_profit = self.tracker.get_today_profit()
        total_positive_profit = self.tracker.get_total_positive_days_profit()
        max_allowed = (total_positive_profit + today_profit) * self.rules.best_day.max_single_day_profit_pct
        
        if today_profit >= max_allowed and total_positive_profit > 0:
            return False, f"BLOCKED: Best day rule - today profit ${today_profit:.2f}"
        return True, ""
    
    def _check_hyperactivity(self, signal, lot_size) -> tuple[bool, str]:
        """Block if approaching request limit"""
        requests = self.tracker.get_today_requests()
        limit = self.rules.hyperactivity.max_requests_per_day - self.rules.safety_buffers.hyperactivity_buffer
        
        if requests >= limit:
            return False, f"BLOCKED: Hyperactivity {requests}/{self.rules.hyperactivity.max_requests_per_day}"
        return True, ""
    
    def emergency_close_all(self) -> list[str]:
        """
        KILL SWITCH - close all positions immediately.
        Called when:
        - Daily loss hits hard limit
        - Overall drawdown hits hard limit
        - Manual /kill command from Telegram
        """
        ...
    
    def monitor_equity_loop(self):
        """
        Background task - continuously monitor equity.
        Auto-triggers emergency_close_all if hard limits breached.
        Runs every 5 seconds.
        """
        ...
```

---

#### [NEW] src/risk/risk_manager.py

```python
class RiskManager:
    """Position sizing and exposure management"""
    
    def calculate_lot_size(self, symbol: str, sl_distance_pips: float) -> float:
        """
        Calculate lot size based on:
        - Account balance × risk_per_trade
        - SL distance in pips
        - Symbol's pip value
        
        Formula: lot = (balance × risk%) / (SL_pips × pip_value_per_lot)
        
        XAUUSD: pip_value = $1.00 per 0.01 lot per pip
        EURUSD: pip_value = $10.00 per 0.1 lot per pip
        """
        ...
    
    def check_correlation(self, new_signal: Signal) -> tuple[bool, str]:
        """
        Prevent overexposure to same currency.
        E.g., LONG EURUSD + LONG GBPUSD = 2x USD short exposure
        """
        ...
    
    def get_max_risk_amount(self) -> float:
        """Current max risk per trade in dollars"""
        return self.account.balance * self.config.risk.risk_per_trade
```

---

#### [NEW] src/risk/daily_tracker.py

```python
class DailyTracker:
    """Track daily PnL, trading days, best day, request counter"""
    
    def reset_daily(self):
        """Called at midnight CE(S)T (FTMO's reset time)"""
        # Save yesterday's data to DB
        # Reset daily counters
        ...
    
    def get_daily_pnl(self) -> float:
        """Current day's realized + unrealized PnL"""
        ...
    
    def get_today_profit(self) -> float:
        """Today's positive PnL only (for best day calc)"""
        ...
    
    def get_total_positive_days_profit(self) -> float:
        """Sum of all positive days' profit"""
        ...
    
    def get_trading_days_count(self) -> int:
        """Number of days with at least 1 trade"""
        ...
    
    def increment_request_count(self):
        """Track MT5 API requests"""
        ...
```

---

#### [NEW] src/core/order_manager.py

```python
class OrderManager:
    """Handle order execution, modification, and trade management"""
    
    async def execute_signal(self, signal: Signal, lot_size: float) -> Trade:
        """
        Execute a trading signal:
        1. Validate with FTMO Guardian
        2. Place order (market or limit)
        3. Set SL and TP1
        4. Log to database
        5. Send Telegram notification
        """
        ...
    
    async def manage_open_trades(self):
        """
        Called every scan interval. For each open trade:
        1. Check if TP1 hit → close partial (50%), move SL to breakeven
        2. Check if TP2 hit → close partial (30%), enable trailing SL
        3. Trailing SL logic after TP2
        """
        ...
    
    async def close_position(self, ticket: int, portion: float = 1.0) -> bool:
        """Close full or partial position"""
        ...
    
    async def modify_sl(self, ticket: int, new_sl: float) -> bool:
        """Modify stop loss (for breakeven or trailing)"""
        ...
```

**Partial TP strategy:**
| Event | Action | Remaining |
|-------|--------|-----------|
| TP1 hit (1.5R) | Close 50%, SL → breakeven | 50% |
| TP2 hit (2.0R) | Close 30%, enable trailing SL | 20% |
| TP3 hit (3.0R) | Close remaining 20% | 0% |
| Trailing SL hit | Close remaining | 0% |

---

#### [NEW] src/telegram/commands.py (Full suite)

```
Command list:

/status          - Balance, equity, margin, open positions, daily PnL
/pnl             - Today/week/month PnL breakdown
/pnl today       - Today's detailed PnL
/trades          - List open trades with entry, SL, TP, current PnL

/auto on         - Enable auto execution (within session)
/auto off        - Disable auto, signal-only mode
/auto            - Show current auto mode status

/risk <value>    - Set risk per trade (e.g., /risk 0.5 for 0.5%)
/risk            - Show current risk settings

/kill            - Emergency close ALL positions
/close <ticket>  - Close specific position
/breakeven <ticket> - Move SL to breakeven for specific trade

/pairs           - List active trading pairs
/pair <symbol> on|off - Enable/disable pair

/session         - Show current session & schedule
/news            - Show upcoming high-impact news

/ftmo            - FTMO dashboard: daily loss, drawdown, best day, trading days
/challenge       - Challenge progress: profit target, current profit, days traded

/backtest <days> - Run backtest for last N days
/report          - Generate performance report

/config          - Show current configuration
/restart         - Restart bot
/ping            - Check bot is alive
```

---

#### [NEW] src/main.py

```python
async def main():
    """Main application entry point"""
    
    # 1. Load config
    config = load_config("config/settings.yaml")
    ftmo_rules = load_ftmo_rules("config/ftmo_rules.yaml")
    
    # 2. Initialize components
    mt5 = MT5Client(config.mt5) if IS_WINDOWS else MT5Mock()
    db = Database(config.system.db_path)
    await db.initialize()
    
    daily_tracker = DailyTracker(db)
    ftmo_guardian = FTMOGuardian(ftmo_rules, daily_tracker, mt5)
    risk_manager = RiskManager(config.risk, mt5)
    smc_engine = SMCEngine(config.strategy)
    session_filter = SessionFilter(config.sessions)
    news_filter = NewsFilter()
    order_manager = OrderManager(mt5, ftmo_guardian, risk_manager, db)
    
    # 3. Start Telegram bot
    telegram_bot = TelegramBot(config.telegram, ...)
    await telegram_bot.start()
    
    # 4. Main trading loop
    while True:
        try:
            # 4a. Check session
            is_session, session_name = session_filter.is_trading_session(utc_now())
            auto_allowed = session_filter.get_auto_trade_allowed(utc_now())
            
            # 4b. Check news
            is_news_blocked, news_reason = news_filter.is_news_blocked(utc_now())
            
            # 4c. Scan for signals (all enabled pairs)
            for pair_config in config.pairs:
                if not pair_config.enabled:
                    continue
                
                # Fetch multi-timeframe data
                data = {
                    "H4": mt5.get_rates(pair_config.symbol, "H4", 200),
                    "H1": mt5.get_rates(pair_config.symbol, "H1", 500),
                    "M15": mt5.get_rates(pair_config.symbol, "M15", 500),
                }
                
                # Run SMC analysis
                signals = smc_engine.analyze(pair_config.symbol, data)
                
                for signal in signals:
                    # Filter
                    if is_news_blocked:
                        logger.info(f"Signal blocked: {news_reason}")
                        continue
                    
                    signal.session = session_name
                    
                    # Auto or Signal mode?
                    if auto_allowed and config.auto_mode:
                        # FTMO Guardian check
                        lot = risk_manager.calculate_lot_size(signal.symbol, signal.sl_distance_pips)
                        approved, reason = ftmo_guardian.can_open_trade(signal, lot)
                        
                        if approved:
                            trade = await order_manager.execute_signal(signal, lot)
                            await telegram_bot.notify_trade_opened(trade)
                        else:
                            logger.warning(f"Trade vetoed: {reason}")
                            await telegram_bot.notify_trade_blocked(signal, reason)
                    else:
                        # Signal-only mode
                        await telegram_bot.notify_signal(signal)
            
            # 4d. Manage open trades (partial TP, trailing SL, breakeven)
            await order_manager.manage_open_trades()
            
            # 4e. FTMO Guardian equity monitor
            ftmo_guardian.monitor_equity()
            
            # 4f. Daily reset check (midnight CE(S)T)
            daily_tracker.check_reset()
            
        except Exception as e:
            logger.critical(f"Main loop error: {e}")
            await telegram_bot.notify_error(e)
        
        await asyncio.sleep(config.system.scan_interval_seconds)
```

---

### Phase 4: Backtesting & Validation (Week 7-8)

#### [NEW] backtest/engine.py

```python
class BacktestEngine:
    """
    Run strategy on historical data.
    Simulates FTMO rules including:
    - Daily loss limit
    - Overall drawdown
    - Best day rule
    - Position sizing
    """
    
    def run(self, symbols: list[str], start_date, end_date, 
            initial_balance: float = 10000) -> BacktestResult:
        """
        Full backtest with FTMO compliance check.
        Returns detailed report with:
        - Total trades, win rate, profit factor
        - Max drawdown, max daily loss
        - Best day check (pass/fail)
        - Equity curve data
        - FTMO challenge simulation (would it pass?)
        """
        ...
```

#### [NEW] backtest/reporter.py

```python
class BacktestReporter:
    """Generate performance reports"""
    
    def generate_report(self, result: BacktestResult) -> str:
        """
        Telegram-formatted report:
        
        📊 BACKTEST REPORT (365 days)
        ──────────────────
        💰 Starting: $10,000 → Final: $12,450
        📈 Total Return: +24.5%
        🎯 Win Rate: 58.3% (142/244)
        📊 Profit Factor: 1.72
        📉 Max Drawdown: 5.8%
        📉 Max Daily Loss: 3.2%
        ⭐ Best Day: $380 (32% of total) ✅ PASS
        📅 Trading Days: 186
        
        🏆 FTMO CHALLENGE SIMULATION:
        Phase 1 (10%): PASS in 23 days
        Phase 2 (5%): PASS in 15 days
        Funded: 8 payouts, avg $620/payout
        """
        ...
```

---

### Phase 5: Deployment & Challenge (Week 9+)

1. **Windows VPS Setup**
   - Contabo/Hetzner Windows VPS ($7-10/mo)
   - Install MT5 terminal + Python 3.11
   - Configure auto-login, auto-start
   - Setup scheduled task to restart bot on crash

2. **FTMO Free Trial**
   - Register FTMO Free Trial (free, same as real challenge)
   - Connect MT5 to FTMO demo server
   - Run bot for 2+ weeks paper trading
   - Validate FTMO Guardian against real FTMO MetriX dashboard

3. **Go Live**
   - Purchase $10K 2-Step Swing challenge (~$155)
   - Monitor closely first 3 days
   - Adjust parameters based on live performance

---

### Phase 6: ML/AI Layer (Month 3-4, separate plan)

Not detailed here. Will create separate plan after Phase 1-5 complete.

High-level:
- Collect 500+ trade signals with outcomes
- Feature engineering: price patterns, volume, volatility, session, time
- Train XGBoost/LightGBM signal quality model
- Score each SMC signal 0-100
- Only execute if confidence ≥ configurable threshold (default 70)

---

## Open Questions

> [!IMPORTANT]
> **Q1**: Bạn đã có FTMO account chưa? Hoặc sẽ đăng ký Free Trial trước?

> [!IMPORTANT]
> **Q2**: Bạn có preference về Telegram bot library? (`python-telegram-bot` vs `aiogram`)
> - `python-telegram-bot`: Phổ biến, documentation tốt, bạn đã dùng cho Sniper Bot
> - `aiogram`: Native async, nhẹ hơn, modern API

> [!NOTE]
> **Q3**: News data source preference?
> - **Finnhub** (free tier, API key required, reliable)
> - **Market Calendar Tool** (scraper, free, may break)
> - **Manual CSV** (stable nhưng không real-time)

---

## Verification Plan

### Automated Tests
```bash
# Unit tests (every module)
pytest tests/ -v --cov=src --cov-report=html

# Critical: FTMO Guardian must have 100% coverage
pytest tests/test_ftmo_guardian.py -v --cov=src/risk/ftmo_guardian.py

# Integration test: full signal → execution pipeline
pytest tests/test_integration.py -v
```

### Backtesting
```bash
# 1-year backtest
python -m backtest --symbols XAUUSD,EURUSD,GBPUSD,USDJPY --days 365

# FTMO challenge simulation
python -m backtest --mode ftmo_challenge --trials 10
```

### Manual Verification
1. **FTMO Free Trial** — Run bot 2 weeks, compare daily PnL with FTMO MetriX
2. **Kill switch test** — Trigger emergency close via `/kill` command
3. **Session filter test** — Verify no auto-trades outside London/NY
4. **News filter test** — Verify blocking around FOMC/NFP
5. **Best day rule test** — Verify bot stops trading when approaching 40% cap
