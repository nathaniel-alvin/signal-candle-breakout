"""
Dynamic scheduler that sleeps until the exact close of the next candle
with a configurable buffer.
"""
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional, Callable

from src.core.config import get_settings

logger = logging.getLogger(__name__)


# Timeframe to seconds mapping
TIMEFRAME_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "12h": 43200,
    "1d": 86400,
    "1w": 604800,
}


class CandleScheduler:
    """Calculates and manages sleep timing for candle-based polling."""

    def __init__(
        self,
        timeframe: str = "1h",
        buffer_seconds: int = 3,
        max_sleep_seconds: int = 3600,
        timezone_str: str = "UTC"
    ):
        self.timeframe = timeframe
        self.buffer_seconds = buffer_seconds
        self.max_sleep_seconds = max_sleep_seconds
        self.timezone_str = timezone_str

        self._interval_seconds = TIMEFRAME_SECONDS.get(timeframe)
        if self._interval_seconds is None:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        logger.info(
            f"Scheduler initialized: timeframe={timeframe} "
            f"({self._interval_seconds}s), buffer={buffer_seconds}s"
        )

    @property
    def interval_seconds(self) -> int:
        return self._interval_seconds

    def get_next_candle_close(self, from_time: Optional[float] = None) -> float:
        """
        Calculate the timestamp of the next candle close.

        Args:
            from_time: Unix timestamp (seconds) to calculate from. Defaults to now.

        Returns:
            Unix timestamp of the next candle close.
        """
        if from_time is None:
            from_time = time.time()

        # Align to interval boundary
        # e.g., for 1h: if now is 10:30, next close is 11:00
        elapsed = from_time % self._interval_seconds
        next_close = from_time + (self._interval_seconds - elapsed)

        return next_close

    def get_sleep_duration(self, from_time: Optional[float] = None) -> float:
        """
        Calculate how long to sleep until next candle close + buffer.

        Args:
            from_time: Unix timestamp to calculate from. Defaults to now.

        Returns:
            Seconds to sleep (capped at max_sleep_seconds).
        """
        next_close = self.get_next_candle_close(from_time)
        sleep_until = next_close + self.buffer_seconds
        sleep_duration = sleep_until - time.time()

        # Handle edge case where we're already past the close + buffer
        if sleep_duration <= 0:
            logger.warning(
                f"Calculated sleep duration <= 0 ({sleep_duration:.2f}s), "
                f"using minimum 1 second"
            )
            sleep_duration = 1.0

        # Cap at max sleep
        if sleep_duration > self.max_sleep_seconds:
            logger.warning(
                f"Sleep duration {sleep_duration:.2f}s exceeds max "
                f"{self.max_sleep_seconds}s, capping"
            )
            sleep_duration = self.max_sleep_seconds

        return sleep_duration

    def sleep_until_next_candle(self, shutdown_check: Optional[Callable[[], bool]] = None) -> float:
        """
        Blocking sleep until next candle close + buffer, with optional interrupt check.

        Args:
            shutdown_check: Optional callable that returns True if shutdown requested.
                           Called periodically during sleep to allow early exit.

        Returns:
            Actual sleep duration in seconds.
        """
        sleep_duration = self.get_sleep_duration()
        next_close = time.time() + sleep_duration - self.buffer_seconds

        logger.debug(
            f"Sleeping {sleep_duration:.2f}s until next candle close "
            f"({datetime.fromtimestamp(next_close, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC)"
        )

        # Sleep in small chunks to allow interrupt checking
        chunk_size = min(10.0, sleep_duration)  # Max 10s chunks
        elapsed = 0.0
        while elapsed < sleep_duration:
            if shutdown_check and shutdown_check():
                logger.debug("Sleep interrupted by shutdown signal")
                break
            chunk = min(chunk_size, sleep_duration - elapsed)
            time.sleep(chunk)
            elapsed += chunk

        return elapsed

    async def async_sleep_until_next_candle(self) -> float:
        """
        Async sleep until next candle close + buffer.

        Returns:
            Actual sleep duration in seconds.
        """
        sleep_duration = self.get_sleep_duration()
        next_close = time.time() + sleep_duration - self.buffer_seconds

        logger.debug(
            f"Async sleeping {sleep_duration:.2f}s until next candle close "
            f"({datetime.fromtimestamp(next_close, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC)"
        )

        await asyncio.sleep(sleep_duration)
        return sleep_duration

    def get_time_until_next_close(self) -> float:
        """Get seconds until next candle close (without buffer)."""
        return self.get_next_candle_close() - time.time()

    def format_next_close(self) -> str:
        """Get formatted string of next candle close time."""
        next_close = self.get_next_candle_close()
        return datetime.fromtimestamp(next_close, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )


def create_scheduler_from_config(settings: Optional["Settings"] = None) -> CandleScheduler:
    """Create scheduler from global config."""
    from src.core.config import get_settings
    settings = settings or get_settings()
    return CandleScheduler(
        timeframe=settings.trading.timeframe,
        buffer_seconds=settings.scheduler.buffer_seconds,
        max_sleep_seconds=settings.scheduler.max_sleep_seconds,
        timezone_str=settings.scheduler.timezone,
    )