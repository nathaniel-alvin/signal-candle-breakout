# CLAUDE.md

# AGENTS.md

## Project
Real-time cryptocurrency breakout signal broadcasting bot.

## Goal
Build a Python application that fetches cryptocurrency market data using ccxt,
detects Momentum Range Breakout signals on closed candles, calculates
Fibonacci-based execution levels, and broadcasts alerts to Telegram and Discord.

## Development Rules

- Inspect the existing repository before modifying anything.
- Preserve the existing architecture unless there is a strong reason to change it.
- Do not rewrite working code unnecessarily.
- Prefer small, incremental changes.
- Keep modules focused on a single responsibility.
- Use type hints.
- Use clear logging.
- Handle network failures gracefully.
- Never hardcode secrets.
- Use environment variables for credentials and webhook URLs.
- Never evaluate the currently forming candle.
- Only evaluate completed candles.
- Avoid duplicate signals for the same candle.
- Add tests for strategy calculations and signal generation.
- Do not remove existing tests unless they are demonstrably obsolete.
- Run tests after making changes.
- Run formatting/linting if configured by the project.
- Do not introduce unnecessary dependencies.

## Trading Strategy

A signal is generated only when all four conditions are satisfied:

1. Strong Body:
   abs(close - open) >= 75% of (high - low)

2. Direction:
   BUY when close > open
   SELL when close < open

3. Volatility Expansion:
   candle range >= 1.2 * SMA(14) of previous candle ranges

4. Base Breakout:
   BUY close > highest high of previous 20 candles
   SELL close < lowest low of previous 20 candles

The breakout lookback must exclude the trigger candle.

## Candle Handling

Only completed candles may be evaluated.

Do not use the currently forming candle for signal generation.

The polling loop should dynamically calculate the time until the next candle closes
and sleep until that time plus a small configurable buffer.

## Risk Management

BUY:

Entry = High - (0.236 * Range)
Stop Loss = Low - (0.10 * ATR14)
Take Profit = High + (0.27 * Range)

SELL:

Entry = Low + (0.236 * Range)
Stop Loss = High + (0.10 * ATR14)
Take Profit = Low - (0.27 * Range)

Calculate and display R:R.

## Notifications

Telegram:
- Telegram Bot API
- sendMessage
- Markdown formatting

Discord:
- Discord webhook
- formatted message or embed

Alerts must contain:

- Symbol
- Timeframe
- Signal
- Entry
- Stop Loss
- Take Profit
- R:R
- Trigger candle High
- Trigger candle Low

## Agent Workflow

Before implementing a feature:

1. Inspect relevant files.
2. Explain what currently exists.
3. Identify the smallest appropriate change.
4. Implement the change.
5. Run relevant tests.
6. Report:
   - files changed
   - what changed
   - tests executed
   - remaining issues

Do not implement unrelated improvements unless requested.

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Signal Candle Jengat** - A real-time cryptocurrency breakout signal broadcasting bot for Telegram and Discord. Uses a Momentum Range Breakout strategy with 4 confirmation conditions and Fibonacci-based execution levels.

### Key Features
- **Strategy**: Momentum Range Breakout with 4 conditions (Strong Body, Directional Match, Volatility Expansion, Base Breakout)
- **Execution Levels**: Fibonacci-based (Entry 0.236 retrace, SL 0.10 ATR buffer, TP 0.27 extension)
- **Notifications**: Telegram (Markdown) + Discord (Rich Embeds)
- **State Persistence**: JSON file survives restarts, prevents duplicate signals
- **Backtesting**: Historical simulation with performance metrics

---

## Commands

### Installation
```bash
cd /home/vin/Dev/signal-candle-jengat
pip install -r requirements.txt
```

### Configuration
```bash
# Copy example config
cp config/settings.yaml config/settings.yaml.local

# Copy env template and add credentials
cp .env.example .env
# Edit .env with Telegram bot token, chat ID, and Discord webhook
```

### Running
```bash
# Live bot (runs continuously)
python main.py

# Run once and exit (for testing)
python main.py --once

# Backtest all configured symbols
python main.py --backtest

# Backtest specific symbols
python main.py --backtest BTC/USDT ETH/USDT

# Test notification channels
python main.py --test-notifications

# Custom config file
python main.py --config config/settings.yaml.local

# Override log level
python main.py --log-level DEBUG
```

### Testing
```bash
# Run pytest (if tests are added)
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=term-missing
```

---

## Architecture

### High-Level Structure
```
signal-candle-jengat/
├── config/
│   ├── settings.yaml          # Main configuration
│   └── settings.yaml.example  # Template
├── src/
│   ├── bot.py                 # Main bot orchestration
│   ├── core/
│   │   ├── config.py          # Pydantic config loader (YAML + env)
│   │   ├── state.py           # State management (JSON persistence)
│   │   ├── scheduler.py       # Candle-close timing
│   │   └── logging_setup.py   # Logging configuration
│   ├── data/
│   │   ├── fetcher.py         # CCXT data fetching with retries
│   │   └── indicators.py      # Technical indicators
│   ├── strategy/
│   │   ├── breakout.py        # Breakout strategy logic
│   │   └── levels.py          # Fibonacci level calculations
│   ├── notifications/
│   │   ├── base.py            # Abstract notifier interface
│   │   ├── telegram.py        # Telegram Bot API
│   │   └── discord.py         # Discord Webhook
│   └── backtest/
│       └── engine.py          # Backtesting engine (stub)
├── main.py                    # Entry point
├── requirements.txt
├── .env.example
└── README.md
```

### Core Components

**Config System** (`src/core/config.py`)
- Pydantic `Settings` class loads from YAML then env vars override
- All settings typed with validation (timeframes, numeric ranges)
- Global instance via `get_settings()` / `reload_settings()`
- Secrets (tokens, webhooks) loaded from `.env` via `get_telegram_token()`, etc.

**State Management** (`src/core/state.py`)
- `StateManager`: Thread-safe with `RLock`, atomic JSON writes via temp file
- Tracks: last processed candle timestamp per symbol, active trades
- `CandleState`: symbol, timestamp, close price
- `ActiveTrade`: side, entry, SL, TP, trigger candle data, exit checking

**Scheduler** (`src/core/scheduler.py`)
- `CandleScheduler`: Calculates sleep until next candle close + buffer
- Sync (`sleep_until_next_candle`) and async variants
- Timeframe mapping: 1m → 1w

**Data Fetcher** (`src/data/fetcher.py`)
- `MarketDataFetcher`: CCXT wrapper with tenacity retry logic
- Exponential backoff with jitter on network/exchange errors
- `fetch_ohlcv_df()`: Returns DataFrame with DatetimeIndex (UTC)
- `fetch_multiple_symbols()`: Sequential fetch with error handling per symbol

**Indicators** (`src/data/indicators.py`)
- All indicator functions return pandas Series
- `add_indicators()`: Adds body_ratio, ATR, range_sma, highest_high/lowest_low, breakout flags
- `get_latest_complete_candle()`: Uses `iloc[-2]` (iloc[-1] is forming candle)
- `validate_dataframe()`: Checks columns, min rows (35+ for indicators + lookback), NaN

**Strategy** (`src/strategy/breakout.py`)
- `BreakoutStrategy`: Evaluates 4 conditions on latest complete candle
- Conditions: strong body (≥75%), directional match, volatility expansion (≥1.2× range SMA), base breakout (close > 20-candle high/low)
- `evaluate()`: Returns `BreakoutSignal` with `SignalType` (BUY/SELL/NONE) and `ExecutionLevels`
- `evaluate_all_candles()`: Vectorized for backtesting

**Levels** (`src/strategy/levels.py`)
- `calculate_levels()`: Fibonacci-based Entry/SL/TP
  - BUY: Entry = High - 0.236×Range, SL = Low - 0.10×ATR, TP = High + 0.27×Range
  - SELL: Entry = Low + 0.236×Range, SL = High + 0.10×ATR, TP = Low - 0.27×Range
- `validate_levels()`: Checks R:R ≥ min_rr and level ordering (SL < Entry < TP for BUY)

**Notifications** (`src/notifications/`)
- `BaseNotifier` (ABC): `send_signal()`, `send_message()`, `test_connection()`
- `NotificationManager`: Aggregates multiple notifiers
- Telegram: `sendMessage` with Markdown parsing
- Discord: Rich embeds with color-coded BUY/SELL, structured fields

**Bot Orchestration** (`src/bot.py`)
- `SignalBot`: Main loop coordinates fetcher → strategy → state → notifications
- Prevents consecutive signals via active trade tracking
- Checks active trade TP/SL on each iteration using forming candle close
- Graceful shutdown with SIGINT/SIGTERM handlers
- `run_once()`: Single iteration for testing

---

## Key Implementation Details

### Candle Processing Logic
1. Fetch `fetch_limit` candles (default 100)
2. Latest complete candle = `df.iloc[-2]` (index -1 is currently forming)
3. Check if candle timestamp > last processed timestamp (state)
4. If new candle: evaluate strategy
5. If signal: update state, record active trade, send notifications
6. If no signal: still update candle state to prevent re-processing
7. Sleep until next candle close + buffer

### Active Trade Tracking
- On signal: record trade with entry, SL, TP, trigger candle data
- On each iteration: check current price (forming candle close) against SL/TP
- If hit: clear trade, send exit notification
- `prevent_consecutive_signals`: Skip new signals while active trade exists

### Configuration Priority
1. YAML file (`config/settings.yaml`)
2. Environment variables (`.env`) — override YAML
3. CLI args (`--log-level`, `--config`) — override both

### Timeframes Supported
`1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d, 1w` (validated in config)

---

## Development Notes

### Adding New Notifiers
1. Create class in `src/notifications/` inheriting `BaseNotifier`
2. Implement `send_signal()`, `send_message()`, `test_connection()`
3. Add factory function `create_xxx_notifier_from_config()`
4. Register in `SignalBot._setup_notifiers()`

### Modifying Strategy
- Parameters in `config/settings.yaml` under `strategy:` and `fibonacci:`
- Logic in `src/strategy/breakout.py` (conditions) and `levels.py` (calculations)
- All parameters accessible via `settings.strategy` and `settings.fibonacci`

### Data Requirements
- Minimum 35 candles for indicators (ATR=14, Range SMA=14, Breakout=20)
- Default fetch limit = 100 provides sufficient history

### Error Handling
- Fetcher: Retries with exponential backoff on network/exchange errors
- State: Corrupted JSON falls back to fresh state (logged warning)
- Main loop: Catches exceptions per symbol, continues processing others
- Notifications: Individual failures logged, don't block other channels

---

## Environment Variables (`.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes* | From @BotFather |
| `TELEGRAM_CHAT_ID` | Yes* | From @userinfobot |
| `DISCORD_WEBHOOK_URL` | Yes* | Discord webhook URL |
| `BINANCE_API_KEY` | No | For authenticated endpoints |
| `BINANCE_API_SECRET` | No | For authenticated endpoints |

*At least one notification channel required for alerts

---

## Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

```bash
docker build -t signal-bot .
docker run -d --env-file .env -v $(pwd)/data:/app/data -v $(pwd)/logs:/app/logs signal-bot
```

---

## Backtesting (Stub)

Backtesting engine exists in `src/backtest/engine.py` but is not yet wired in `main.py`. To enable:
1. Uncomment imports in `main.py`
2. Implement `run_backtest_from_config()` in engine
3. Add CLI logic for `--backtest` flag (currently commented)
