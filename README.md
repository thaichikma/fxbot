# FXBot - FTMO MT5 Trading System

FXBot is an automated MT5 trading bot specifically designed for FTMO prop firm challenges ($10k 2-Phase Swing). It leverages Smart Money Concepts (SMC) to detect high-probability market setups alongside strict "Guardian"-level risk limits explicitly matching FTMO's parameters.

## Key Features
- **SMC Strategy Core**: Automated detection of Order Blocks, FVGs, BOS/CHoCH structures, and Liquidity Sweeps on multi-timeframes.
- **FTMO Guardian**: Real-time Kill Switch to avoid Daily Loss (5%), Overall Drawdown (10%), and Hyperactivity violations. Features safety buffers to intervene before FTMO strikes.
- **Session & News Filtering**: Only hunts setups inside high-probability windows (e.g. London & NY overlap) avoiding major red-folder news.
- **Hybrid Execution**: "Auto Mode" via VPS during prime windows and "Signal Mode" for low-quality alerts sent through a Telegram bot shell.

## Documentation
- [Kiến trúc giả lập trading — data / strategy / backtest / metrics](docs/simulation-architecture.md)
- [Project Overview & PDR](docs/project-overview-pdr.md)
- [System Architecture](docs/system-architecture.md)
- [Codebase Summary](docs/codebase-summary.md)
- [Code Standards](docs/code-standards.md)
- [Project Roadmap](docs/project-roadmap.md)
- [Deployment (Windows VPS + FTMO)](docs/deployment.md)

## Development Setup (MacOS)
```bash
# Setup uv venv
uv venv
source .venv/bin/activate
uv pip install -r requirements-dev.txt

# Run Tests
pytest tests/
```

## Production Deployment
Chạy trên **Windows VPS** với MT5 Terminal và biến môi trường trong `.env`. Chi tiết: [docs/deployment.md](docs/deployment.md) và [scripts/windows/README.md](scripts/windows/README.md).

## Telegram — backtest
- `/backtest` hoặc `/bt`: chạy backtest với CSV mặc định (`backtest.default_csv` trong `config/settings.yaml`; repo có `data/backtest/sample_m15.csv`).
- `/backtest help` — hướng dẫn; `/backtest status` — kiểm tra symbol và file mặc định.

## Backtest — phí giao dịch (xấp xỉ)
- `backtest.costs`: spread (`symbols.yaml`), commission RT/lot (mặc định ~**$5**/lot forex theo thông tin FTMO kiểu ECN), swap đêm (mặc định long/short âm vài USD/lot — **ước lượng**). **Không** thay tick thật; vàng/CFD cần chỉnh tay (FTMO có thể tính %).

## Database — OHLC đa khung (MTF) & giả lập

- Bảng `ohlc_bars` (symbol, tf, ts, OHLC, volume): lưu nhiều khung (M1…MN1) để đánh giá trend / walk-forward không chỉ resample từ M15.
- Bảng `simulation_runs` / `simulation_steps`: ghi equity + `metrics_json` theo từng nến (tham số tùy chỉnh: ADX, bias, …).
- Schema được tạo cùng `data/fxbot.db` khi bot khởi động; có thể dùng đồng bộ qua `MTFOHLCStore`.
- Nạp CSV: `PYTHONPATH=. uv run python scripts/mtf_import_csv.py --symbol XAUUSD --all-xau` (hoặc liệt kê file; `--max-rows` để giới hạn).

## Backtest — XAUUSD (CSV MT4 trong `data/`)
- Định dạng: `Date;Open;High;Low;Close;Volume` (dấu `;`, ngày kiểu `YYYY.MM.DD HH:MM`). Loader đọc tự động.
- **Chỉ cần M15** cho `python -m backtest`: H1/H4 được tạo từ M15 trong engine. Các file 1h, 4h, 1d, … phục vụ phân tích / đối chiếu, không nạp song song vào backtest hiện tại.
- Ví dụ (giới hạn số nến cho tốc độ):  
  `PYTHONPATH=. python -m backtest --symbol XAUUSD --csv data/XAU_15m_data.csv --max-bars 50000 --from-date 2024-01-01 --step 4`
- Thống kê nhanh các file `XAU_*.csv`: `PYTHONPATH=. python scripts/xau_data_info.py`
