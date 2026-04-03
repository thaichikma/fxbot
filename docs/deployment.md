# FXBot — Triển khai production (Windows VPS + FTMO)

Tài liệu này mô tả cách chạy FXBot trên **Windows VPS** cùng **MetaTrader 5**, chuỗi **FTMO Free Trial / Demo**, và checklist **go-live** challenge trả phí. Code bot (`MetaTrader5` Python) **chỉ chạy trên Windows** khi kết nối terminal thật.

## Mục lục

1. [Kiến trúc triển khai](#1-kiến-trúc-triển-khai)
2. [Chuẩn bị VPS Windows](#2-chuẩn-bị-vps-windows)
3. [Cài đặt MT5 và tài khoản FTMO](#3-cài-đặt-mt5-và-tài-khoản-ftmo)
4. [Python, mã nguồn và biến môi trường](#4-python-mã-nguồn-và-biến-môi-trường)
5. [Chạy bot và Scheduled Task](#5-chạy-bot-và-scheduled-task)
6. [FTMO Free Trial / Demo (2+ tuần)](#6-ftmo-free-trial--demo-2-tuần)
7. [Go-live challenge trả phí](#7-go-live-challenge-trả-phí)
8. [Vận hành, giám sát, khẩn cấp](#8-vận-hành-giám-sát-khẩn-cấp)
9. [Xử lý sự cố](#9-xử-lý-sự-cố)

---

## 1. Kiến trúc triển khai

| Thành phần | Vai trò |
|------------|---------|
| **Windows VPS** | OS bắt buộc cho `MetaTrader5` (Python) + MT5 Terminal GUI |
| **MT5 Terminal** | Đăng nhập FTMO; EA/bridge; dữ liệu tick/candles |
| **FXBot (Python)** | Vòng lặp quét tín hiệu SMC, Guardian, lệnh qua `OrderManager`, Telegram |
| **Telegram** | Điều khiển (`/auto`, `/exec`, `/kill`, …), cảnh báo |

**Lưu ý:** MT5 thường cần **phiên đăng nhập Windows tương tác** (desktop session). VPS “headless” thuần không GUI thường **không phù hợp** trừ khi bạn đã xác nhận broker/FTMO cho phép và terminal chạy ổn trong cấu hình đó. Khuyến nghị: VPS Windows có desktop, RDP, tự đăng nhập hoặc luôn mở session sau reboot.

---

## 2. Chuẩn bị VPS Windows

### 2.1 Nhà cung cấp và quy mô

- **RAM:** tối thiểu 2 GB (4 GB thoải mái hơn cho MT5 + Python).
- **Ổ đĩa:** 40 GB+ SSD.
- **Vùng:** gần server FTMO/EU giảm độ trễ nếu có thể.
- **Hệ điều hành:** Windows Server hoặc Windows 10/11 (bản được host hỗ trợ).

### 2.2 Bảo mật cơ bản

- Đổi port RDP mặc định hoặc dùng VPN / firewall chỉ cho IP của bạn.
- Bật Windows Update; antivirus nhẹ (tránh xung đột với MT5).
- **Không** lưu mật khẩu FTMO/Telegram trong chat công khai; dùng `.env` trên máy và quyền file hạn chế.

### 2.3 Thời gian hệ thống

- Đặt múi giờ rõ ràng; bot và `session_filter` dùng **UTC** trong logic — cần đồng bộ với cấu hình `sessions` và Finnhub (news) như đã mô tả trong `config/settings.yaml`.

---

## 3. Cài đặt MT5 và tài khoản FTMO

1. Tải **MetaTrader 5** từ trang chính thức hoặc qua FTMO (đúng bản họ khuyến nghị).
2. Cài đặt terminal (đường dẫn mặc định thường là `C:\Program Files\MetaTrader 5\terminal64.exe`).
3. Trong MT5: **File → Login to Trade Account** — nhập login/password/server do FTMO cung cấp (Demo / Free Trial / Challenge).
4. Xác nhận **Algo Trading** được bật nếu broker yêu cầu; kiểm tra kết nối và hiển thị số dư.

Gán vào `.env` (xem `.env.example`):

- `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER` — trùng với tài khoản đang mở trong terminal.
- `MT5_PATH` — đường dẫn đầy đủ tới `terminal64.exe`.

---

## 4. Python, mã nguồn và biến môi trường

### 4.1 Python

- Cài **Python 3.11+** (64-bit) từ python.org hoặc Windows Store.
- Khuyến nghị: **venv** riêng cho project.

### 4.2 Clone / copy mã nguồn

Đặt repo ở đường dẫn cố định, ví dụ `C:\fxbot`.

### 4.3 Dependencies

```powershell
cd C:\fxbot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Trên Windows, `requirements.txt` sẽ cài `MetaTrader5`.

### 4.4 Biến môi trường

1. Copy `.env.example` → `.env`.
2. Điền đầy đủ: MT5, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `FINNHUB_API_KEY`.
3. Đặt `ENV=production`.

### 4.5 Cấu hình an toàn mặc định

Trong `config/settings.yaml`, khóa **`system.execution_enabled`** mặc định là `false` — bot **không** gửi lệnh thật cho đến khi bạn bật có chủ đích (sau test). Có thể bật tạm qua Telegram `/exec` khi đã tin cậy pipeline (xem bot commands).

Chạy kiểm tra nhanh (tùy chọn):

```powershell
.\scripts\windows\preflight.ps1 -ProjectRoot C:\fxbot
```

---

## 5. Chạy bot và Scheduled Task

### 5.1 Chạy thủ công

Từ thư mục gốc repo:

```powershell
cd C:\fxbot
.\.venv\Scripts\Activate.ps1
python -m src.main
```

Hoặc dùng wrapper:

```powershell
.\scripts\windows\run-fxbot.ps1 -ProjectRoot C:\fxbot
```

### 5.2 Tự khởi động sau khi đăng nhập Windows

Script đăng ký **Task Scheduler** (chạy khi user log on — phù hợp MT5 cần desktop):

```powershell
# PowerShell Admin (tuỳ chọn — một số máy không cần)
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\scripts\windows\register-scheduled-task.ps1 -ProjectRoot C:\fxbot
```

Gỡ task:

```powershell
.\scripts\windows\unregister-scheduled-task.ps1
```

**Gợi ý:** Trong Task Scheduler, có thể chỉnh **“Restart on failure”** (tùy bản Windows) hoặc dùng công cụ như NSSM để chạy như service — chỉ khi bạn đã xác nhận MT5 hoạt động trong môi trường không GUI.

---

## 6. FTMO Free Trial / Demo (2+ tuần)

Mục tiêu: xác nhận bot không vi phạm quy tắc FTMO và số liệu gần với **MetriX** / dashboard.

| Bước | Việc cần làm |
|------|----------------|
| 1 | Đăng ký **FTMO Free Trial** hoặc **Demo** cùng loại challenge dự định (Swing / 2-Step). |
| 2 | Giữ `execution_enabled` tắt hoặc rủi ro cực nhỏ cho tuần đầu; quan sát Telegram và log. |
| 3 | So sánh **daily PnL / drawdown / số lệnh** với FTMO — điều chỉnh `ftmo_rules.yaml`, session, news nếu lệch. |
| 4 | Kiểm tra **kill switch** (`/kill`), **session** (không auto ngoài cửa sổ), **news block** quanh tin quan trọng. |
| 5 | Tối thiểu **2 tuần** dữ liệu trước khi nộp phí challenge. |

---

## 7. Go-live challenge trả phí

| Bước | Việc cần làm |
|------|----------------|
| 1 | Mua challenge đúng loại (ví dụ $10K 2-Step Swing) trên site FTMO. |
| 2 | Cập nhật `MT5_*` trong `.env` trỏ tài khoản challenge mới; khởi động lại MT5 + bot. |
| 3 | Xác nhận `challenge_phase` / `challenge_type` trong `config/settings.yaml` khớp **Phase 1**. |
| 4 | **72 giờ đầu:** giám sát sát; có thể giảm `risk_per_trade`, tắt `/auto` ngoài giờ vàng. |
| 5 | Ghi chép tham số thay đổi và lý do (spread, slippage, symbol). |

---

## 8. Vận hành, giám sát, khẩn cấp

- **Log:** thư mục `logs/` (theo `system.log_dir`).
- **Database:** `data/fxbot.db` — backup định kỳ nếu cần audit.
- **Telegram:** luôn có thể tắt thực thi (`/exec`), đóng lệnh (`/kill`), xem `/challenge`, `/trades`.
- **Mất RDP / reboot:** đảm bảo MT5 + bot tự mở lại (Scheduled Task + “Start MT5 on startup” nếu cần).

---

## 9. Xử lý sự cố

| Hiện tượng | Hướng xử lý |
|------------|-------------|
| `Failed to connect to MT5` | Kiểm tra terminal đã mở và đăng nhập; `MT5_PATH` đúng; firewall. |
| Không có lệnh dù có tín hiệu | `execution_enabled`, `/auto`, session, news block, Guardian kill switch. |
| Lệch MetriX | Timezone, rollover ngày, cách tính equity; đối chiếu từng ngày. |
| Bot thoát sau vài giây | Xem log; chạy `preflight.ps1`; kiểm tra thiếu biến `.env`. |

---

## Tham chiếu nhanh

| File / đường dẫn | Mô tả |
|------------------|--------|
| `src/main.py` | Entry: `python -m src.main` |
| `config/settings.yaml` | `execution_enabled`, sessions, risk |
| `config/ftmo_rules.yaml` | Ngưỡng FTMO + buffer |
| `scripts/windows/*.ps1` | Chạy và đăng ký task trên Windows |
| `docs/project-roadmap.md` | Roadmap tổng thể |

---

*Tài liệu này bổ sung cho Phase 5 (Deployment); không thay thế điều khoản FTMO hoặc hướng dẫn chính thức của broker.*
