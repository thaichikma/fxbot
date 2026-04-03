# Scripts Windows (FXBot)

| Script | Mô tả |
|--------|--------|
| `run-fxbot.ps1` | Kích hoạt `.venv` và chạy `python -m src.main` |
| `preflight.ps1` | Kiểm tra venv, `.env`, import `MetaTrader5` |
| `register-scheduled-task.ps1` | Đăng ký task **At log on** (cần PowerShell **Run as Administrator**) |
| `unregister-scheduled-task.ps1` | Gỡ task (Admin) |

Hướng dẫn đầy đủ: [`docs/deployment.md`](../../docs/deployment.md).
