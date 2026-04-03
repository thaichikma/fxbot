# Kiến trúc — giả lập & phân tích giao dịch

Tài liệu tham chiếu: phân lớp, chỉ số, sai lầm thường gặp, quy trình — và **FXBot đang ở đâu** trong từng phần.

---

## 1. Data Layer (dữ liệu)

| Yêu cầu | Mô tả | FXBot hiện tại |
|--------|--------|----------------|
| **Timezone** | Một chuẩn (UTC) end-to-end | `load_ohlc_csv` → `time` UTC; MT4 `YYYY.MM.DD` → parse UTC |
| **OHLC đa khung** | Nguồn thật, đồng bộ | CSV; **SQLite `ohlc_bars`** (`MTFOHLCStore`), slice cửa sổ; import: `scripts/mtf_import_csv.py`, `src/data/mtf_csv_import.py` |
| **Volume** | Phục vụ ML / lưu trữ | Cột `Volume` / `tick_volume` trong CSV → `volume` khi load và khi insert DB |
| **Spread** | Theo symbol/broker | `symbols.yaml` + `backtest.costs.spread_mode` |
| **Commission / swap** | Ước lượng trong backtest | `backtest.costs.*` — XAU/CFD nên chỉnh tay |
| **Slippage** | Tin, biến động | **Chưa** mô hình slippage ngẫu nhiên — fill OHLC trong bar (SL trước nếu cùng nến) |

**Import CSV → DB:** `--all-xau` nạp mọi `data/XAU_*_data.csv`; map TF theo tên file (hậu tố **dài trước** để `15m` không khớp nhầm `5m`).

---

## 2. Strategy Engine (logic)

- Tách khỏi vòng lặp nến: engine gọi được từ scanner (live) và có thể từ backtest (tương đương rule).

| Module | Vai trò |
|--------|---------|
| `SMCEngine` | SMC: H4 bias, H1 structure, M15 FVG — pandas, không dùng `smartmoneyconcepts` |
| `H1M5Engine` | H1 EMA(12/26) trend; M5 FVG cùng rule gap với SMC |
| `MLEngine` | XGBoost pickle (RSI/ATR/volume features) → `ML_PREDICTION` nếu `ml.enabled` + `model_path` |
| `risk` trong `settings.yaml` | `risk_per_trade` → sizing trong backtest |

**Cấu hình pair:** `strategy: smc | h1_m5 | ml` (mặc định `smc`). Crypto mẫu (BTC/ETH) dùng `h1_m5` + `enabled: false` cho đến khi broker có symbol.

**Scanner** (`src/strategy/scanner.py`): theo từng pair, load đúng khung MT5 (`H4/H1/M15` hoặc `H1/M5` hoặc `M15` cho ML).

---

## 3. Backtest Engine (máy giả lập)

| Nguyên tắc | FXBot |
|------------|--------|
| **Không lookahead** | Walk-forward theo index M15; signal tại `i`, exit từ sau `i` |
| **Độ phân giải** | Entry SMC trên **M15**; exit có thể **M1** nếu có `--m1-csv` / `backtest.m1_csv` |
| **Fill / path** | Conservative: cùng nến chạm SL trước nếu SL và TP cùng chạm | `backtest/engine.py` `_simulate_exit` / `_simulate_exit_m1` |

---

## 4. Metrics (đánh giá)

| Chỉ số | Ý nghĩa |
|--------|---------|
| Profit Factor, Max DD, Win rate | Trong reporter |
| **Expectancy** | $/trade — `backtest/metrics_extra.py` |
| **Sharpe** (tùy) | Từ daily returns — `metrics_extra.py` |

---

## 5. Kiểm thử trên dữ liệu thật

| Test | Mô tả |
|------|--------|
| `tests/test_real_data_csv.py` | Đọc CSV trong `data/` (sample M15, XAU tùy chọn), chạy engine / ML features |
| `tests/test_real_data_from_db.py` | Import CSV → `ohlc_bars` (DB tạm), đọc `fetch_last_n` → backtest / ML |
| `tests/test_data_loader_mt4.py` | Loader MT4 + slice |

Marker: `pytest -m real_data`. Biến môi trường: xem docstring trong các file test.

---

## 6. Sai lầm thường gặp

1. **Overfitting** — giảm: walk-forward, ít tham số, out-of-sample.
2. **Không chia mẫu** — có `--from-date` / `--to-date` / `--max-bars`; chưa script train/test cố định.
3. **Bỏ qua spread** — nhất là XAU; chỉnh `costs` + `symbols.yaml`.

---

## 7. Quy trình tham chiếu

1. Backtest CLI / Telegram  
2. Walk-forward (DB `simulation_runs` / `simulation_steps` có thể ghi log)  
3. Monte Carlo — chưa có module riêng  

---

## 8. Sơ đồ luồng (tóm tắt)

```text
CSV / MT5 → (optional) ohlc_bars → StrategyEngine → Signals / Backtest
                                      ↓
                         Trades + equity → Metrics (PF, DD, E, Sharpe)
```

---

*Tài liệu mô tả kiến trúc triển khai; không thay thế tài liệu FTMO/broker chính thức.*
