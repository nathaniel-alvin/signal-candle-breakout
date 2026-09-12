# Signal Candle Jengat

Real-time cryptocurrency breakout signal broadcasting bot for Telegram and Discord.

## Features

- **Momentum Range Breakout Strategy** with 4 confirmation conditions
- **Fibonacci-based execution levels** (Entry, SL, TP with R:R calculation)
- **Multi-channel notifications**: Telegram (Markdown) + Discord (Rich Embeds)
- **State persistence**: Survives restarts, prevents duplicate signals
- **Backtesting engine**: Historical simulation with performance metrics
- **Robust error handling**: Retry logic, rate limiting, graceful shutdown

## Strategy Logic

A signal triggers only on the **close of a completed candle** satisfying all four conditions:

1. **Strong Body**: Real body ≥ 75% of full candle range
2. **Directional Match**: Bullish (close > open) for BUY, Bearish for SELL
3. **Volatility Expansion**: Candle range ≥ 1.2× 14-period SMA of ranges
4. **Base Breakout**: Close breaks above 20-candle high (BUY) or below 20-candle low (SELL)

### Execution Levels (Fibonacci-based)

| Level | Long (BUY) | Short (SELL) |
|-------|------------|--------------|
| **Entry** | High - (0.236 × Range) | Low + (0.236 × Range) |
| **Stop Loss** | Low - (0.10 × ATR) | High + (0.10 × ATR) |
| **Take Profit** | High + (0.27 × Range) | Low - (0.27 × Range) |

## Quick Start

### 1. Install Dependencies

```bash
cd /home/vin/Dev/signal-candle-jengat
pip install -r requirements.txt
```

### 2. Configure

```bash
# Copy example config
cp config/settings.yaml config/settings.yaml.local

# Copy env template and add your credentials
cp .env.example .env
# Edit .env with your Telegram bot token, chat ID, and Discord webhook
```

### 3. Run

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

## Configuration

### Required Environment Variables (`.env`)

```env
TELEGRAM_BOT_TOKEN=your_bot_token_from_BotFather
TELEGRAM_CHAT_ID=your_chat_id
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

### Key Settings (`config/settings.yaml`)

```yaml
trading:
  symbols: ["BTC/USDT", "ETH/USDT", "BNB/USDT"]
  timeframe: "1h"
  fetch_limit: 100

strategy:
  strong_body_pct: 0.75      # 75% body requirement
  volatility_multiplier: 1.2 # 1.2x range SMA
  breakout_lookback: 20      # 20-candle high/low
  atr_period: 14
  range_sma_period: 14

fibonacci:
  entry_retrace: 0.236       # 23.6% pullback entry
  sl_atr_multiplier: 0.10    # 10% ATR buffer
  tp_extension: 0.27         # 27% extension target
```

## Project Structure

```
signal-candle-jengat/
├── config/
│   ├── settings.yaml          # Main configuration
│   └── settings.yaml.example  # Template
├── src/
│   ├── bot.py                 # Main bot orchestration
│   ├── core/
│   │   ├── config.py          # Pydantic config loader
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
│       └── engine.py          # Backtesting engine
├── main.py                    # Entry point
├── requirements.txt
├── .env.example
└── README.md
```

## Backtesting

```bash
# Full backtest with 500 candles per symbol
python main.py --backtest --limit 1000

# Results include:
# - Win rate, profit factor, max drawdown
# - Average P&L, consecutive wins/losses
# - Per-trade details with entry/exit prices
```

## Notifications

### Telegram (Markdown)
```
🟢 BUY Signal — BTC/USDT (1h)
━━━━━━━━━━━━━━━━━━━━
**Entry:** `45230.123456`
**Stop Loss:** `44890.123456`
**Take Profit:** `45890.123456`
**R:R Ratio:** `2.15`
━━━━━━━━━━━━━━━━━━━━
*Trigger Bar:* High `45300.00` | Low `44800.00`
*Range:* `500.00` | *ATR(14):* `320.50`
*Time:* 2024-01-15 14:00:00 UTC
```

### Discord (Rich Embed)
- Color-coded (Green for BUY, Red for SELL)
- Structured fields for all levels
- Timestamp and footer branding

## State Persistence

Bot state is saved to `data/bot_state.json`:
- Last processed candle timestamp per symbol
- Active trades (for consecutive signal prevention)

## Logging

Logs to both console and `logs/bot.log` with rotation (10MB, 5 backups).

## Docker (Optional)

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

## License

MIT