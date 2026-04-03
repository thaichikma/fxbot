# 🧠 Brainstorm Report: MT5 Trading System for FTMO

**Date:** 2026-04-03  
**Project:** fxbot  
**Status:** Awaiting approval for implementation plan

---

## 1. Problem Statement

Build một hệ thống giao dịch tự động trên nền tảng MetaTrader 5, nhắm mục tiêu pass FTMO prop firm challenge và duy trì funded account. Hệ thống cần tuân thủ nghiêm ngặt các quy tắc FTMO trong khi tối đa hóa lợi nhuận ổn định.

### Confirmed Requirements

| Aspect | Decision |
|--------|----------|
| **Instruments** | XAUUSD (Gold) + Forex Majors (EURUSD, GBPUSD, USDJPY) |
| **Strategy** | SMC + Session Filter → Roadmap ML/AI |
| **FTMO Type** | 2-Step Challenge, $10K, Swing Account |
| **Automation** | Hybrid Mode (Auto session + Signal ngoài giờ) |
| **Tech Stack** | Python + Windows VPS |
| **Risk** | 1% per trade, Telegram Bot monitoring |

---

## 2. FTMO Rules — Hard Constraints

Hệ thống **PHẢI** tuân thủ 100%. Vi phạm bất kỳ rule nào = mất challenge/funded account.

| Rule | Limit ($10K Account) | System Response |
|------|----------------------|-----------------|
| Max Daily Loss | 5% = **$500** | Kill switch tự động khi PnL ngày ≤ -$400 (buffer 20%) |
| Max Overall Loss | 10% = **$1,000** | Kill switch khi equity ≤ $9,100 (buffer 10%) |
| Best Day Rule | Best day < 50% tổng profit | TP cap per day, phân bổ profit đều |
| Min Trading Days | 4 ngày | Bot đảm bảo trade ít nhất 4 ngày riêng biệt |
| Hyperactivity | < 2,000 requests/day | Rate limiter trên order operations |
| Inactivity | ≥ 1 trade / 30 ngày | Heartbeat trade nếu bot idle |

---

## 3. Evaluated Architectures

### Option A: Monolithic Python Script
```
┌─────────────────────────────────────┐
│           main.py (single file)     │
│  ┌─────────────────────────────┐    │
│  │ MT5 Connection              │    │
│  │ Data Fetching               │    │
│  │ Strategy Logic (SMC)        │    │
│  │ Risk Management             │    │
│  │ Order Execution             │    │
│  │ Telegram Bot                │    │
│  └─────────────────────────────┘    │
└─────────────────────────────────────┘
```

| Pros | Cons |
|------|------|
| ⚡ Nhanh build MVP | 🔴 Không test được từng module |
| 📄 Đơn giản | 🔴 Spaghetti code khi scale |
| | 🔴 Không thể thêm ML/AI layer sau |

**Verdict: ❌ Reject** — Vi phạm DRY, không scale được.

---

### Option B: Modular Monolith (Recommended ⭐)
```
fxbot/
├── config/
│   ├── settings.yaml          # Account config, pairs, sessions
│   └── ftmo_rules.yaml        # FTMO hard limits
├── core/
│   ├── mt5_client.py          # MT5 connection & data
│   ├── strategy/
│   │   ├── base.py            # Abstract strategy interface
│   │   ├── smc_engine.py      # SMC: BOS, CHoCH, OB, FVG, Liquidity
│   │   └── session_filter.py  # London/NY session + News filter
│   ├── risk_manager.py        # Position sizing, daily PnL, drawdown guard
│   ├── order_manager.py       # Order execution, modification, SL/TP
│   └── ftmo_guardian.py       # FTMO rule enforcement (the "safety valve")
├── signals/
│   ├── scanner.py             # Multi-pair signal scanner
│   └── signal_types.py        # Signal dataclass definitions
├── telegram/
│   ├── bot.py                 # Telegram command handler
│   ├── commands.py            # /status, /risk, /auto, /kill, /pnl
│   └── notifications.py      # Alert formatting
├── data/
│   ├── db.py                  # SQLite trade log & state
│   └── models.py              # Trade, Signal, DailyPnL models
├── backtest/
│   ├── engine.py              # Historical backtesting engine
│   └── reporter.py            # Performance metrics & charts
├── main.py                    # Entry point, main loop
├── requirements.txt
└── docs/
```

| Pros | Cons |
|------|------|
| ✅ Mỗi module test riêng được | 🟡 Setup ban đầu lâu hơn Option A |
| ✅ `ftmo_guardian` chặn mọi lệnh vi phạm | |
| ✅ Dễ thêm ML/AI module sau | |
| ✅ Pattern giống Sniper Bot Binance — quen tay | |
| ✅ Config-driven, thay đổi pair/settings không cần code | |

**Verdict: ✅ Recommended**

---

### Option C: Microservices (Python + MQL5)
```
┌──────────────┐     Socket/File     ┌──────────────┐
│ Python Brain │ ◄──────────────────► │  MQL5 EA     │
│ (Signal Gen) │     IPC Bridge      │ (Executor)   │
└──────────────┘                     └──────────────┘
       │
       ▼
  ┌──────────┐
  │ Telegram │
  └──────────┘
```

| Pros | Cons |
|------|------|
| ✅ MQL5 execution = lowest latency | 🔴 Phải học MQL5 |
| ✅ Separation of concerns | 🔴 IPC bridge = thêm failure point |
| | 🔴 Debug khó hơn nhiều |
| | 🔴 Overkill cho non-HFT strategy |

**Verdict: ❌ Reject** — Over-engineering. Latency 50-200ms của Python API đủ cho SMC strategy.

---

## 4. Final Architecture: Modular Monolith (Option B)

### 4.1 System Flow

```
                    ┌─────────────────────────────────────────┐
                    │              MAIN LOOP                   │
                    │         (async event loop)               │
                    └─────────┬───────────────────┬───────────┘
                              │                   │
                 ┌────────────▼────────┐  ┌───────▼──────────┐
                 │   MT5 Client        │  │  Telegram Bot     │
                 │ • connect/reconnect │  │  • /status        │
                 │ • fetch OHLCV       │  │  • /auto on|off   │
                 │ • tick subscription  │  │  • /risk <val>    │
                 │ • account info      │  │  • /kill          │
                 └────────────┬────────┘  │  • /pnl           │
                              │           │  • /pairs          │
                 ┌────────────▼────────┐  └───────────────────┘
                 │   Signal Scanner     │
                 │ • Multi-pair scan    │
                 │ • Multi-timeframe    │
                 └────────────┬────────┘
                              │
              ┌───────────────▼───────────────┐
              │       SMC Engine               │
              │ • Market Structure (BOS/CHoCH) │
              │ • Order Blocks detection       │
              │ • Fair Value Gaps (FVG)        │
              │ • Liquidity Sweeps             │
              │ • Supply/Demand Zones          │
              └───────────────┬───────────────┘
                              │
              ┌───────────────▼───────────────┐
              │       Session Filter           │
              │ • London (14:00-21:00 VN)      │
              │ • New York (19:30-02:00 VN)    │
              │ • News calendar filter         │
              │ • Asian session = signal only  │
              └───────────────┬───────────────┘
                              │
              ┌───────────────▼───────────────┐
              │      FTMO Guardian 🛡️          │
              │ • Daily PnL check             │
              │ • Overall drawdown check      │
              │ • Best Day profit cap         │
              │ • Hyperactivity counter       │
              │ • Trading days tracker        │
              │ ⚠️ CAN VETO ANY ORDER         │
              └───────────────┬───────────────┘
                              │
              ┌───────────────▼───────────────┐
              │      Risk Manager              │
              │ • Position sizing (1% risk)    │
              │ • SL distance → lot calc       │
              │ • Max concurrent positions     │
              │ • Correlation check (Gold≈USD) │
              └───────────────┬───────────────┘
                              │
                  ┌───────────▼───────────┐
                  │    Order Manager       │
                  │ • market/limit/stop    │
                  │ • partial TP           │
                  │ • trailing SL          │
                  │ • breakeven move       │
                  └───────────────────────┘
```

### 4.2 FTMO Guardian — Module quan trọng nhất

```python
# Pseudo-code concept
class FTMOGuardian:
    """Safety valve - chặn mọi lệnh vi phạm FTMO rules"""
    
    def can_open_trade(self, signal) -> tuple[bool, str]:
        # 1. Daily loss check
        if self.daily_pnl <= -self.daily_loss_buffer:  # -$400
            return False, "BLOCKED: Approaching daily loss limit"
        
        # 2. Overall drawdown check  
        if self.equity <= self.min_equity:  # $9,100
            return False, "BLOCKED: Approaching max drawdown"
        
        # 3. Best day profit cap
        if self.today_profit >= self.max_day_profit:
            return False, "BLOCKED: Best day rule - stop for today"
        
        # 4. Hyperactivity check
        if self.today_requests >= 1800:  # buffer trước 2000
            return False, "BLOCKED: Approaching hyperactivity limit"
        
        # 5. Max concurrent positions
        if self.open_positions >= self.max_positions:
            return False, "BLOCKED: Max concurrent positions reached"
        
        return True, "APPROVED"
    
    def emergency_close_all(self):
        """Kill switch - đóng tất cả vị thế ngay lập tức"""
        ...
```

### 4.3 SMC Engine Components

| Component | Timeframe | Mô tả |
|-----------|-----------|-------|
| **Market Structure** | H1 + M15 | Xác định BOS (Break of Structure), CHoCH (Change of Character) |
| **Order Blocks** | H1 → M15 entry | Vùng giá institutional order, entry tại OB pullback |
| **Fair Value Gap** | M15 | Gap 3 nến, entry khi giá fill FVG |
| **Liquidity Sweep** | H1 | Detect quét đỉnh/đáy → reversal signal |
| **Supply/Demand** | H4 + H1 | Vùng cung cầu lớn cho bias direction |

### 4.4 Session & News Filter

```
Session Schedule (Vietnam Time UTC+7):

Sydney:    05:00 - 14:00  → ❌ Không trade (low vol)
Tokyo:     06:00 - 15:00  → ❌ Không trade (low vol, wide spread Gold)
London:    14:00 - 23:00  → ✅ AUTO MODE
New York:  19:30 - 04:00  → ✅ AUTO MODE  
Overlap:   19:30 - 23:00  → ⭐ PRIME TIME (best setups)

News Filter:
- Fetch economic calendar (ForexFactory/Investing.com API)
- Block trading 15min trước & 15min sau High Impact news
- FOMC, NFP, CPI = block 30min trước/sau
```

### 4.5 Risk Manager — Position Sizing

```
Position Size Formula:

lot_size = (account_balance × risk_pct) / (SL_distance_points × point_value)

Example (XAUUSD, $10K account, 1% risk, SL = 50 pips):
lot_size = ($10,000 × 0.01) / (50 × $1.0) = 0.02 lots

Example (EURUSD, $10K account, 1% risk, SL = 30 pips):
lot_size = ($10,000 × 0.01) / (30 × $10.0) = 0.033 lots → round to 0.03
```

---

## 5. ML/AI Roadmap (Phase 2)

Sau khi system core ổn định (2-3 tháng), layer thêm ML:

```
Phase 2 Architecture Addition:
                              
┌──────────────────────────────┐
│        ML Signal Layer       │
│ • Feature engineering        │
│   (price action patterns,    │
│    volume, volatility,       │
│    session context)          │
│ • Model: XGBoost/LightGBM   │
│   (trade quality scoring)    │
│ • Signal confidence: 0-100%  │
│ • Only execute if score ≥ 70 │
└──────────────┬───────────────┘
               │
               ▼
    ┌──────────────────┐
    │ SMC Engine output │ → ML scores → Filter low-quality signals
    └──────────────────┘
```

**ML Use Cases:**
1. **Signal Quality Scoring** — Score mỗi SMC signal 0-100, chỉ trade score cao
2. **Optimal Session Detection** — ML tìm window tốt nhất từng pair
3. **Dynamic Risk Sizing** — Tăng/giảm lot theo confidence score
4. **Pattern Recognition** — Detect OB/FVG patterns mà rule-based miss

---

## 6. Tech Stack Summary

| Layer | Technology | Lý do |
|-------|-----------|-------|
| **Language** | Python 3.11+ | Ecosystem, async, ML-ready |
| **MT5 API** | `MetaTrader5` package | Official, stable |
| **Async** | `asyncio` + `aiohttp` | Non-blocking main loop |
| **Data** | `pandas` + `numpy` | OHLCV processing |
| **Indicators** | `pandas-ta` | SMC calculations |
| **Database** | SQLite (`aiosqlite`) | Trade log, state, PnL history |
| **Telegram** | `python-telegram-bot` | Control & monitoring |
| **Config** | YAML (`pyyaml`) | Settings management |
| **Scheduling** | `APScheduler` | Session schedules, daily reset |
| **Logging** | `loguru` | Structured logging |
| **Deployment** | Windows VPS (Contabo/Hetzner) | MT5 terminal 24/7 |
| **ML (Phase 2)** | `scikit-learn`, `xgboost` | Signal quality scoring |

---

## 7. Implementation Phases

### Phase 1: Foundation (Week 1-2)
- [ ] Project structure setup
- [ ] MT5 client (connect, fetch data, account info)
- [ ] Config system (YAML)
- [ ] SQLite database models
- [ ] Basic Telegram bot shell
- [ ] FTMO Guardian module

### Phase 2: Strategy Core (Week 3-4)
- [ ] Market Structure detection (BOS/CHoCH)
- [ ] Order Block identification
- [ ] FVG detection
- [ ] Liquidity Sweep detection
- [ ] Session Filter
- [ ] Signal Scanner (multi-pair)

### Phase 3: Execution & Risk (Week 5-6)
- [ ] Risk Manager (position sizing, correlation)
- [ ] Order Manager (entry, SL, TP, trailing, breakeven)
- [ ] Hybrid mode logic (auto/signal switch)
- [ ] Telegram commands full suite
- [ ] News filter integration

### Phase 4: Backtesting & Validation (Week 7-8)
- [ ] Backtest engine with historical data
- [ ] Performance reporter (win rate, PF, max DD, Sharpe)
- [ ] Best Day Rule simulation
- [ ] FTMO rule compliance validation
- [ ] Paper trading on demo account

### Phase 5: Challenge (Week 9+)
- [ ] Deploy to Windows VPS
- [ ] Run on FTMO demo/Free Trial
- [ ] Fine-tune parameters
- [ ] Start real challenge khi win rate ≥ 55% & PF ≥ 1.5

### Phase 6: ML/AI Layer (Month 3-4)
- [ ] Collect trade data (signals, outcomes, context)
- [ ] Feature engineering
- [ ] Train signal quality model
- [ ] A/B test: SMC only vs SMC + ML filter
- [ ] Deploy if statistically significant improvement

---

## 8. Success Metrics

| Metric | Target | Đo bằng |
|--------|--------|---------|
| **Win Rate** | ≥ 55% | Backtest + Paper trading |
| **Profit Factor** | ≥ 1.5 | Total profit / Total loss |
| **Max Drawdown** | ≤ 6% | Không bao giờ gần 10% limit |
| **Daily Drawdown** | ≤ 3% | Buffer lớn trước 5% limit |
| **Best Day / Total** | ≤ 40% | Buffer trước 50% rule |
| **Avg Trades/Day** | 2-5 | Đủ nhưng không hyperactive |
| **Challenge Pass Rate** | ≥ 60% | Qua 3/5 attempts |
| **Monthly Return** | 5-10% | Sustainable on funded account |

---

## 9. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| 🔴 MT5 disconnect / VPS down | Mất control lệnh đang mở | Heartbeat monitor + Telegram alert + SL luôn set sẵn |
| 🔴 Bug trong FTMO Guardian | Vi phạm rule → mất account | Unit test 100% coverage cho module này, integration test |
| 🟡 Slippage / requote | Entry/SL không đúng giá | Limit order thay vì market order khi có thể |
| 🟡 Strategy underperform live | Backtest ≠ live | Paper trade tối thiểu 2 tuần trước real challenge |
| 🟡 News spike xuyên SL | Loss lớn hơn expected | News filter + max position size hard cap |
| 🟢 Mac dev → Windows prod gap | Code behave khác | Docker dev environment + CI test |

---

## 10. Key Differences from Sniper Bot (Binance)

| Aspect | Sniper Bot (Binance) | FXBot (MT5/FTMO) |
|--------|---------------------|-------------------|
| Market | Crypto Futures | Forex + Gold |
| API | REST + WebSocket | MT5 Python Package |
| Trading hours | 24/7 | Session-based |
| Risk rules | Self-imposed | **FTMO-enforced** (fail = lose account) |
| Order types | Limit (GTX maker) | Market + Limit + Stop |
| Leverage | Configurable | Fixed by broker/FTMO |
| Swap/Rollover | Funding rate | Overnight swap (Swing OK) |
| Spread | BBO spread | Variable spread (session-dependent) |
| **New module needed** | — | FTMO Guardian, Session Filter, News Filter |

---

## 11. Next Step

> ❓ **Bạn muốn tôi tạo Implementation Plan chi tiết để bắt đầu build?**
