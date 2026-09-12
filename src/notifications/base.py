"""
Base notification classes and interfaces.
"""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from src.strategy.breakout import BreakoutSignal

logger = logging.getLogger(__name__)


@dataclass
class NotificationResult:
    """Result of a notification send attempt."""
    success: bool
    message: str
    error: Optional[str] = None


class BaseNotifier(ABC):
    """Abstract base class for notification channels."""

    def __init__(self, name: str, enabled: bool = True, timeout: int = 10):
        self.name = name
        self.enabled = enabled
        self.timeout = timeout

    @abstractmethod
    def send_signal(self, signal: BreakoutSignal) -> NotificationResult:
        """Send a breakout signal notification."""
        pass

    @abstractmethod
    def send_message(self, message: str) -> NotificationResult:
        """Send a generic text message."""
        pass

    @abstractmethod
    def test_connection(self) -> NotificationResult:
        """Test the notification channel connection."""
        pass

    def _format_signal_message(self, signal: BreakoutSignal) -> str:
        """Format signal for text-based notification."""
        if not signal.is_valid() or signal.levels is None:
            return f"⚠️ Invalid signal for {signal.symbol}"

        levels = signal.levels
        emoji = "🟢" if levels.side.value == "BUY" else "🔴"
        timestamp = signal.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC") if signal.timestamp else "N/A"

        return (
            f"{emoji} **{levels.side.value} Signal** — {signal.symbol} ({signal.timeframe})\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"**Entry:** `{levels.entry:.6f}`\n"
            f"**Stop Loss:** `{levels.stop_loss:.6f}`\n"
            f"**Take Profit:** `{levels.take_profit:.6f}`\n"
            f"**R:R Ratio:** `{levels.risk_reward_ratio:.2f}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"*Trigger Bar:* High `{levels.trigger_high:.6f}` | Low `{levels.trigger_low:.6f}`\n"
            f"*Range:* `{levels.trigger_range:.6f}` | *ATR(14):* `{levels.atr_value:.6f}`\n"
            f"*Time:* {timestamp}"
        )

    def _check_enabled(self) -> Optional[NotificationResult]:
        """Check if notifier is enabled."""
        if not self.enabled:
            return NotificationResult(
                success=False,
                message=f"{self.name} notifier is disabled",
                error="Disabled in config"
            )
        return None


class NotificationManager:
    """Manages multiple notification channels."""

    def __init__(self):
        self.notifiers: list[BaseNotifier] = []

    def add_notifier(self, notifier: BaseNotifier) -> None:
        """Add a notifier to the manager."""
        self.notifiers.append(notifier)
        logger.info(f"Added notifier: {notifier.name}")

    def send_signal(self, signal: BreakoutSignal) -> list[NotificationResult]:
        """Send signal to all enabled notifiers."""
        results = []
        for notifier in self.notifiers:
            if notifier.enabled:
                try:
                    result = notifier.send_signal(signal)
                    results.append(result)
                    if result.success:
                        logger.info(f"Signal sent via {notifier.name}")
                    else:
                        logger.warning(f"Failed to send via {notifier.name}: {result.error}")
                except Exception as e:
                    logger.error(f"Error sending via {notifier.name}: {e}")
                    results.append(NotificationResult(False, "", str(e)))
            else:
                logger.debug(f"Skipping disabled notifier: {notifier.name}")
        return results

    def send_message(self, message: str) -> list[NotificationResult]:
        """Send generic message to all enabled notifiers."""
        results = []
        for notifier in self.notifiers:
            if notifier.enabled:
                try:
                    result = notifier.send_message(message)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Error sending message via {notifier.name}: {e}")
                    results.append(NotificationResult(False, "", str(e)))
        return results

    def test_all(self) -> list[NotificationResult]:
        """Test all notifiers."""
        results = []
        for notifier in self.notifiers:
            if notifier.enabled:
                try:
                    result = notifier.test_connection()
                    results.append(result)
                except Exception as e:
                    results.append(NotificationResult(False, "", str(e)))
        return results