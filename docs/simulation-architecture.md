# Kiến trúc chuẩn — hệ thống giả lập giao dịch

Tài liệu tham chiếu: phân lớp, chỉ số, sai lầm thường gặp, quy trình pro — và **FXBot đang ở đâu** trong từng phần.

---

## 1. Data Layer (dữ liệu)

| Yêu cầu | Mô tả | FXBot hiện tại |
|--------|--------|----------------|
| **Timezone** | Một chuẩn (UTC) end-to-end; tránh lệch phiên | `load_ohlc_csv` → `time` UTC; MT4 `YYYY.MM.DD` → parse UTC |
| **OHLC đa khung** | Nguồn thật, đồng bộ | CSV + DB `ohlc_bars` (`MTFOHLCStore`), slice theo cửa sổ |
| **Spread** | Theo symbol/broker (XAU khác EUR nhiều) | `symbols.yaml` + `backtest.costs.spread_mode` (typical / …) |
| **Commission** | RT/lot hoặc % notional (CFD) | `commission_usd_per_lot_round_turn` — **ước lượng**; XAU nên chỉnh tay |
| **Slippage** | Đặc biệt tin; XAU biến động mạnh | **Chưa** mô hình slippage ngẫu nhiên / theo volatility — fill trong `engine` là OHLC bar (conservative SL trước) |

**Hướng cải thiện data:** thêm tham số `slippage_points` / phân phối; tách `spread_bps` theo từng năm nếu có dữ liệu.

---

## 2. Strategy Engine (logic)

- Định nghĩa tín hiệu (entry), SL/TP, sizing (risk %).
- **Tách khỏi** vòng lặp nến: cùng một engine gọi được từ backtest và (sau này) live.

| FXBot | Ghi chú |
|-------|---------|
| `SMCEngine` | SMC: H4 bias, H1 structure, M15 FVG — không phải EMA+RSI |
| `risk` trong `settings.yaml` | `risk_per_trade` → sizing qua equity (backtest engine) |

Thay đổi chiến lược = module strategy mới hoặc mở rộng `SMCEngine`, không trộn vào lớp “fill order”.

---

## 3. Backtest Engine (máy giả lập)

| Nguyên tắc | FXBot |
|------------|--------|
| **Không lookahead** | Chỉ dùng dữ liệu đến `t` (walk-forward theo index nến); signal tại `i`, exit từ `i+1` |
| **Độ phân giải** | Entry SMC trên M15; exit có thể trên M1 (đường đi SL/TP chi tiết hơn) | CLI `--m1-csv` hoặc `backtest.m1_csv` trong `settings.yaml` → `engine` gọi `_simulate_exit_m1`; không có M1 thì `_simulate_exit` trên M15 |
| **Fill / path** | Conservative: cùng nến chạm SL trước nếu cả SL và TP | Có trong `backtest/engine.py` |

---

## 4. Metrics (đánh giá)

Không chỉ **profit**; tối thiểu:

| Chỉ số | Ý nghĩa |
|--------|---------|
| **Profit Factor** | Gross win / gross loss |
| **Max Drawdown** | Quan trọng với FTMO / tâm lý |
| **Win rate** | Cần kèm avg win/loss |
| **Expectancy** | \(E \approx (WR \times AvgWin) - (LR \times \|AvgLoss\|)\) trên $/trade — **E > 0** là điều kiện cần (dài hạn) |
| **Sharpe** (tùy) | Từ chuỗi equity / daily return; annualized ~ \(\sqrt{252}\) |

Code: `backtest/metrics_extra.py` — expectancy, Sharpe từ `BacktestResult`.

---

## 5. Sai lầm thường gặp

1. **Overfitting** — tối ưu tham số trên toàn bộ quá khứ → live kém.  
   **Giảm:** train/test/forward, ít tham số, walk-forward, Monte Carlo.

2. **Không chia mẫu** — ví dụ Train 2019–2023, Test 2024, Forward 2025.  
   **FXBot:** có thể dùng `--from-date` / `--to-date` / `--max-bars`; **chưa** script train/test cố định.

3. **Bỏ qua spread/slippage** — nhất là XAU.  
   **FXBot:** có spread+commission+swap trong backtest; **thiếu** slippage ngẫu nhiên.

---

## 6. Quy trình “pro” (tham chiếu)

1. **Backtest cơ bản** — toàn bộ hoặc một khúc (đã có CLI + Telegram).  
2. **Walk-forward** — train → test → lặp; DB `simulation_runs` / `simulation_steps` hỗ trợ ghi log.  
3. **Monte Carlo** — xáo trộn thứ tự lệnh / slippage / equity path — **chưa** có module; có thể thêm sau.

---

## 7. Sơ đồ luồng (tóm tắt)

```text
Data (UTC, OHLC, costs) → Strategy Engine → Backtest loop (no lookahead)
                                    ↓
                          Trades + Equity curve
                                    ↓
              Metrics (PF, DD, WR, Expectancy, Sharpe, FTMO hints)
```

---

*Tài liệu này mô tả kiến trúc mục tiêu; không thay thế tài liệu FTMO/broker chính thức.*
