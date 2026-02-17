# Bitfa Trader 🤖

Automated crypto futures trading bot that copies signals from BITFA Futures Telegram channel to LBank exchange.

## Architecture

```
Telegram Channel (BITFA Futures)
    ↓ Telethon
Signal Parser (Groq — GPT OSS 20B)
    ↓
Position Manager (Django)
    ↓
LBank Futures API
    ↓
PostgreSQL (positions, orders, signals)
```

## Stack

- **Django 6.0.2** — Backend + Admin dashboard
- **Telethon** — Telegram MTProto client (private channel listener)
- **Groq** — LLM for signal parsing (GPT OSS 20B)
- **LBank Futures API** — Order execution
- **Celery + Redis** — Background tasks (order sync, PnL tracking)
- **PostgreSQL** — Production database (SQLite for dev)

## Quick Start

### 1. Setup

```bash
cd "Bitfa Trader"
cp .env.example .env
# Edit .env with your API keys
uv sync
```

### 2. Database

```bash
uv run python manage.py migrate
uv run python manage.py createsuperuser
```

### 3. Run

```bash
# Start the bot (dry run mode — no real trades)
uv run python manage.py runbot --dry-run

# Start for real
uv run python manage.py runbot

# Start Celery worker (order sync)
uv run celery -A config worker -l info -B
```

### 4. Admin Panel

```bash
uv run python manage.py runserver
# Visit http://localhost:8000/admin
```

## Signal Format

The bot parses signals like:

```
Lbank Futures 🔴SHORT
📈 #ETH/USDT
📍 Enter price: 1966.3 🦅 1986.4
✅ TP1: 1944.5
🟢 TP2: 1921.8
🟢 TP3: 1901
🔴 Normal Stop Loss: 2009.1
⚠️ 1% Risk (Isolated 8X)
```

And follow-up updates:
- Entry achieved notifications
- Risk management (Persian) instructions
- TP hit notifications with profit %
- Position close commands

## Environment Variables

See `.env.example` for all available settings.

Key ones:
- `LBANK_API_KEY` / `LBANK_SECRET_KEY` — Exchange API credentials
- `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` — Telegram app credentials
- `SIGNAL_CHANNEL_ID` — Telegram channel to listen to
- `GROQ_API_KEY` — Groq API for signal parsing
- `DEFAULT_RISK_PERCENT` — Default risk % per trade (1.0)
- `MAX_OPEN_POSITIONS` — Maximum concurrent positions (5)
