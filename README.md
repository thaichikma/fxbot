# FXBot - FTMO MT5 Trading System

FXBot is an automated MT5 trading bot for FTMO-style prop challenges. It uses **Smart Money Concepts (SMC)** and optional **H1/M5 trend + FVG**, **ML scoring (XGBoost/LSTM)**, and strict **FTMO Guardian** risk limits.

## Key Features

- **Strategy profiles** (per pair in `config/settings.yaml` → `strategy:`):
  - **`smc`** (default): H4 bias, H1 structure, M15 FVG — `SMCEngine`.
  - **`h1_m5`**: H1 EMA trend, M5 FVG — `H1M5Engine` (e.g. crypto).
  - **`ml`**: optional XGBoost model from `ml.model_path` — `MLEngine`.
- **FTMO Guardian**: kill switch for daily loss, overall drawdown, hyperactivity; safety buffers.
- **Session & news filtering**: London/NY windows; optional Finnhub calendar blocking.
- **Hybrid execution**: auto mode during allowed sessions vs signal-only via Telegram.
- **Portfolio**: forex, XAU, optional **BTCUSD / ETHUSD** (`symbols.yaml`; pairs `enabled: false` until your broker offers symbols).

## Documentation

| Doc | Content |
|-----|---------|
| [simulation-architecture.md](docs/simulation-architecture.md) | Data, strategies, backtest resolution, metrics, pitfalls |
| [deployment.md](docs/deployment.md) | Windows VPS, MT5, FTMO, go-live |
| [project-overview-pdr.md](docs/project-overview-pdr.md) | PDR |
| [system-architecture.md](docs/system-architecture.md) | System view |
| [codebase-summary.md](docs/codebase-summary.md) | Repo layout |
| [code-standards.md](docs/code-standards.md) | Conventions |
| [project-roadmap.md](docs/project-roadmap.md) | Roadmap |
| [scripts/windows/README.md](scripts/windows/README.md) | Windows scripts |

## Development Setup (macOS / Linux)

```bash
uv venv
source .venv/bin/activate   # or: .venv\Scripts\activate on Windows
uv pip install -r requirements-dev.txt

# Optional ML training (XGBoost + PyTorch)
uv pip install -r requirements-ml.txt

pytest tests/
```

### Tests using your CSV / database

- **CSV**: `tests/test_real_data_csv.py` — reads `data/XAU_*_data.csv`, `data/backtest/sample_m15.csv`. Env: `FXBOT_TEST_MAX_BARS`, `FXBOT_TEST_CSV`, `FXBOT_TEST_SYMBOL`.
- **SQLite `ohlc_bars`**: `tests/test_real_data_from_db.py` — imports CSVs into a temp DB then runs backtest / ML features from `MTFOHLCStore`. Env: `FXBOT_TEST_DB_MAX_ROWS`, `FXBOT_TEST_SKIP_DB_IMPORT=1` to skip.

## Production Deployment

Run on **Windows VPS** with MT5 terminal and `.env`. See [docs/deployment.md](docs/deployment.md) and [scripts/windows/README.md](scripts/windows/README.md).

## Telegram

- `/backtest`, `/bt`: backtest default CSV (`backtest.default_csv` in `settings.yaml`; sample: `data/backtest/sample_m15.csv`).
- `/backtest help`, `/backtest status` — help and config (includes `m1_csv` if set).
- Other commands: `/auto`, `/exec`, `/risk`, `/trades`, `/session`, `/config`, `/challenge` — see bot help.

## Backtest CLI

```text
python -m backtest --symbol XAUUSD --csv data/XAU_15m_data.csv [--m1-csv data/XAU_1m_data.csv] [--max-m15-exit 96] [--from-date YYYY-MM-DD] [--to-date ...] [--max-bars N] [--step 4]
```

- **Entry**: SMC on **M15** (H1/H4 resampled inside engine from M15).
- **Exit**: if `--m1-csv` or `backtest.m1_csv` points to a valid M1 CSV (aligned in time with M15), SL/TP path is simulated on **M1**; otherwise on M15.
- **Costs**: `backtest.costs` — spread from `symbols.yaml`, commission RT/lot, overnight swap (approximate; tune for XAU/CFD).

## Data: CSV → SQLite (MTF)

- Table **`ohlc_bars`**: `(symbol, tf, ts, OHLC, volume, source)` — M1 … MN1.
- **Import** (development / analysis):

  ```bash
  PYTHONPATH=. python scripts/mtf_import_csv.py --db data/fxbot.db --symbol XAUUSD --all-xau --replace
  PYTHONPATH=. python scripts/mtf_import_csv.py --db data/fxbot.db data/XAU_15m_data.csv --max-rows 100000
  ```

- TF is inferred from filename (`XAU_15m_data.csv` → M15). Longest suffix wins so **`15m` is not mistaken for `5m`**.
- **Info script**: `PYTHONPATH=. python scripts/xau_data_info.py`

## Machine learning (optional)

- **Features**: RSI, ATR, volume (log) — `src/ml/features.py`, `src/ml/indicators.py`.
- **Train**:

  ```bash
  PYTHONPATH=. python scripts/ml_train.py --csv data/backtest/sample_m15.csv --model xgb --out models/xgb.pkl
  PYTHONPATH=. python scripts/ml_train.py --csv path/to/m15.csv --model lstm --out models/lstm.pt
  ```

- Enable in **`settings.yaml`** → `ml:` (`enabled`, `model_path`, `prob_threshold`, …) and set a pair to `strategy: ml`.

## XAU CSV (MT4-style)

- Format: `Date;Open;High;Low;Close;Volume` — semicolon, date `YYYY.MM.DD HH:MM`. Loader auto-detects.
- Large files can be sliced with `--max-bars` / backtest `--max-bars`.
