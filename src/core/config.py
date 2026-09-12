"""
Configuration loader with Pydantic validation.
Loads from YAML file and environment variables.
"""
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ExchangeConfig(BaseModel):
    name: str = "binance"
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    enable_rate_limit: bool = True
    timeout: int = 30000


class TradingConfig(BaseModel):
    symbols: List[str] = Field(default_factory=lambda: ["BTC/USDT", "ETH/USDT"])
    timeframe: str = "1h"
    fetch_limit: int = 100

    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, v: str) -> str:
        valid = {"1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w"}
        if v not in valid:
            raise ValueError(f"Invalid timeframe: {v}. Must be one of {valid}")
        return v


class StrategyConfig(BaseModel):
    strong_body_pct: float = 0.75
    volatility_multiplier: float = 1.2
    breakout_lookback: int = 20
    atr_period: int = 14
    range_sma_period: int = 14

    @field_validator("strong_body_pct", "volatility_multiplier")
    @classmethod
    def validate_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Must be positive")
        return v

    @field_validator("breakout_lookback", "atr_period", "range_sma_period")
    @classmethod
    def validate_positive_int(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Must be positive integer")
        return v


class FibonacciConfig(BaseModel):
    entry_retrace: float = 0.236
    sl_atr_multiplier: float = 0.10
    tp_extension: float = 0.27


class StateConfig(BaseModel):
    persist_enabled: bool = True
    persist_file: str = "data/bot_state.json"
    prevent_consecutive_signals: bool = True
    track_active_trades: bool = True


class SchedulerConfig(BaseModel):
    buffer_seconds: int = 3
    max_sleep_seconds: int = 3600
    timezone: str = "UTC"


class TelegramConfig(BaseModel):
    enabled: bool = True
    bot_token: Optional[str] = None
    chat_id: Optional[str] = None
    parse_mode: str = "Markdown"
    timeout: int = 10


class DiscordConfig(BaseModel):
    enabled: bool = True
    webhook_url: Optional[str] = None
    timeout: int = 10
    embed_color_buy: int = 3066993
    embed_color_sell: int = 15158332
    embed_color_info: int = 3447003


class NotificationsConfig(BaseModel):
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    date_format: str = "%Y-%m-%d %H:%M:%S"
    file_enabled: bool = True
    file_path: str = "logs/bot.log"
    file_max_bytes: int = 10485760
    file_backup_count: int = 5
    console_enabled: bool = True

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid}")
        return v_upper


class RetryConfig(BaseModel):
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: int = 2
    jitter: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    exchange: ExchangeConfig = Field(default_factory=ExchangeConfig)
    trading: TradingConfig = Field(default_factory=TradingConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    fibonacci: FibonacciConfig = Field(default_factory=FibonacciConfig)
    state: StateConfig = Field(default_factory=StateConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Settings":
        """Load settings from YAML file, then override with env vars."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path, "r") as f:
            yaml_data = yaml.safe_load(f) or {}

        # Create instance with YAML data, env vars will override via BaseSettings
        return cls(**yaml_data)

    def get_telegram_token(self) -> Optional[str]:
        """Get Telegram bot token from env or config."""
        return os.getenv("TELEGRAM_BOT_TOKEN") or self.notifications.telegram.bot_token

    def get_telegram_chat_id(self) -> Optional[str]:
        """Get Telegram chat ID from env or config."""
        return os.getenv("TELEGRAM_CHAT_ID") or self.notifications.telegram.chat_id

    def get_discord_webhook(self) -> Optional[str]:
        """Get Discord webhook URL from env or config."""
        return os.getenv("DISCORD_WEBHOOK_URL") or self.notifications.discord.webhook_url

    def get_binance_api_key(self) -> Optional[str]:
        """Get Binance API key from env or config."""
        return os.getenv("BINANCE_API_KEY") or self.exchange.api_key

    def get_binance_api_secret(self) -> Optional[str]:
        """Get Binance API secret from env or config."""
        return os.getenv("BINANCE_API_SECRET") or self.exchange.api_secret


# Global settings instance
_settings: Optional[Settings] = None


def get_settings(config_path: Optional[str | Path] = None) -> Settings:
    """Get or create global settings instance."""
    global _settings
    if _settings is None:
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config" / "settings.yaml"
        _settings = Settings.from_yaml(config_path)
    return _settings


def reload_settings(config_path: Optional[str | Path] = None) -> Settings:
    """Force reload settings from file."""
    global _settings
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "config" / "settings.yaml"
    _settings = Settings.from_yaml(config_path)
    return _settings