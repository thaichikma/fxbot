# FXBot - FTMO MT5 Trading System

FXBot is an automated MT5 trading bot specifically designed for FTMO prop firm challenges ($10k 2-Phase Swing). It leverages Smart Money Concepts (SMC) to detect high-probability market setups alongside strict "Guardian"-level risk limits explicitly matching FTMO's parameters.

## Key Features
- **SMC Strategy Core**: Automated detection of Order Blocks, FVGs, BOS/CHoCH structures, and Liquidity Sweeps on multi-timeframes.
- **FTMO Guardian**: Real-time Kill Switch to avoid Daily Loss (5%), Overall Drawdown (10%), and Hyperactivity violations. Features safety buffers to intervene before FTMO strikes.
- **Session & News Filtering**: Only hunts setups inside high-probability windows (e.g. London & NY overlap) avoiding major red-folder news.
- **Hybrid Execution**: "Auto Mode" via VPS during prime windows and "Signal Mode" for low-quality alerts sent through a Telegram bot shell.

## Documentation
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
- Trong `config/settings.yaml`, mục `backtest.costs`: spread (theo `symbols.yaml`), commission/lot, swap qua đêm — **không** thay thế tick thật hay 100% khớp FTMO; chỉnh `commission_*` / `swap_*` theo spec broker.
