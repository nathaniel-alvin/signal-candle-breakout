"""
Market data fetching using CCXT with retry logic and rate limit handling.
"""
import logging
from typing import List, Optional, Dict, Any

import ccxt
import pandas as pd
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception_type,
    before_sleep_log,
    RetryCallState,
)

from src.core.config import get_settings

logger = logging.getLogger(__name__)


# Create a retry decorator factory that can be used with instance methods
def create_retry_decorator(max_retries: int, base_delay: float, max_delay: float):
    """Create a tenacity retry decorator with the given config."""
    return retry(
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential_jitter(
            initial=base_delay,
            max=max_delay,
            jitter=1.0,
        ),
        retry=retry_if_exception_type((
            ccxt.NetworkError,
            ccxt.ExchangeError,
            ccxt.RequestTimeout,
            TimeoutError,
            ConnectionError,
        )),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


class MarketDataFetcher:
    """Fetches OHLCV data from exchanges using CCXT with robust error handling."""

    def __init__(
        self,
        exchange_name: str = "binance",
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        enable_rate_limit: bool = True,
        timeout: int = 30000,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
    ):
        self.exchange_name = exchange_name
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

        # Create retry decorator for this instance
        self._retry_decorator = create_retry_decorator(max_retries, base_delay, max_delay)

        # Initialize exchange
        exchange_class = getattr(ccxt, exchange_name)
        self.exchange = exchange_class({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": enable_rate_limit,
            "timeout": timeout,
            "options": {
                "defaultType": "spot",
            },
        })

        logger.info(f"Initialized {exchange_name} exchange for market data")

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100,
        since: Optional[int] = None,
    ) -> List[List[float]]:
        """
        Fetch OHLCV candles with retry logic.

        Args:
            symbol: Trading pair (e.g., "BTC/USDT")
            timeframe: Candle timeframe (e.g., "1h")
            limit: Number of candles to fetch
            since: Timestamp in milliseconds to fetch from

        Returns:
            List of [timestamp, open, high, low, close, volume]
        """
        logger.debug(f"Fetching {limit} {timeframe} candles for {symbol}")

        # Apply retry logic using the instance's decorator
        @self._retry_decorator
        def _fetch():
            return self.exchange.fetch_ohlcv(symbol, timeframe, since, limit)

        return _fetch()

    def fetch_ohlcv_df(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100,
        max_candle_age_seconds: int = 3600,
    ) -> pd.DataFrame:
        """
        Fetch OHLCV data as a pandas DataFrame with proper types.

        Args:
            symbol: Trading pair
            timeframe: Candle timeframe
            limit: Number of candles
            max_candle_age_seconds: Max age of latest complete candle before rejecting as stale

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
            Index is DatetimeIndex (UTC)

        Raises:
            ValueError: If data is stale, empty, or invalid
        """
        ohlcv = self.fetch_ohlcv(symbol, timeframe, limit)

        if not ohlcv:
            raise ValueError(f"No data returned for {symbol} {timeframe}")

        df = pd.DataFrame(
            ohlcv,
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        )

        # Convert timestamp to datetime index
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df.set_index("timestamp", inplace=True)

        # Ensure numeric types
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # Drop any rows with NaN
        df.dropna(inplace=True)

        if df.empty:
            raise ValueError(f"All rows dropped due to NaN for {symbol} {timeframe}")

        # Check data freshness: latest complete candle is iloc[-2]
        if len(df) >= 2:
            latest_complete_ts = df.index[-2]
            age_seconds = (pd.Timestamp.now(tz="UTC") - latest_complete_ts).total_seconds()
            if age_seconds > max_candle_age_seconds:
                raise ValueError(
                    f"Stale data for {symbol} {timeframe}: latest complete candle is "
                    f"{age_seconds:.0f}s old (max allowed: {max_candle_age_seconds}s)"
                )
            logger.debug(
                f"Data freshness OK for {symbol}: latest complete candle age={age_seconds:.0f}s"
            )
        else:
            raise ValueError(f"Insufficient candles for freshness check: {len(df)} rows")

        logger.debug(f"Fetched {len(df)} candles for {symbol} {timeframe}")
        return df

    def fetch_multiple_symbols(
        self,
        symbols: List[str],
        timeframe: str = "1h",
        limit: int = 100,
        max_candle_age_seconds: int = 3600,
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch data for multiple symbols sequentially.

        Args:
            symbols: List of trading pairs
            timeframe: Candle timeframe
            limit: Number of candles per symbol
            max_candle_age_seconds: Max age of latest complete candle before rejecting as stale

        Returns:
            Dict mapping symbol to DataFrame (empty DataFrame on error)
        """
        results = {}
        for symbol in symbols:
            try:
                results[symbol] = self.fetch_ohlcv_df(
                    symbol, timeframe, limit, max_candle_age_seconds
                )
            except Exception as e:
                logger.error(f"Failed to fetch {symbol}: {e}")
                results[symbol] = pd.DataFrame()  # Empty DataFrame on error
        return results

    def get_current_price(self, symbol: str) -> float:
        """
        Get current ticker price for a symbol.

        Args:
            symbol: Trading pair

        Returns:
            Current price as float
        """
        @self._retry_decorator
        def _fetch_ticker():
            return self.exchange.fetch_ticker(symbol)

        ticker = _fetch_ticker()
        return float(ticker["last"])

    def get_exchange_info(self) -> Dict[str, Any]:
        """Get exchange info including rate limits."""
        return {
            "name": self.exchange.name,
            "rate_limit": getattr(self.exchange, "rateLimit", None),
            "has_fetch_ohlcv": self.exchange.has.get("fetchOHLCV", False),
            "timeframes": list(self.exchange.timeframes.keys()) if self.exchange.timeframes else [],
        }

    def close(self) -> None:
        """Close exchange connections."""
        if hasattr(self.exchange, "close"):
            self.exchange.close()
        logger.debug("Exchange connection closed")


def create_fetcher_from_config(settings: Optional["Settings"] = None) -> MarketDataFetcher:
    """Create fetcher from global config."""
    from src.core.config import get_settings
    settings = settings or get_settings()
    return MarketDataFetcher(
        exchange_name=settings.exchange.name,
        api_key=settings.get_binance_api_key(),
        api_secret=settings.get_binance_api_secret(),
        enable_rate_limit=settings.exchange.enable_rate_limit,
        timeout=settings.exchange.timeout,
        max_retries=settings.retry.max_attempts,
        base_delay=settings.retry.base_delay,
        max_delay=settings.retry.max_delay,
    )
