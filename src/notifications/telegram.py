"""
Telegram Bot API notification implementation.
"""
import logging
import requests
from typing import Optional

from src.notifications.base import BaseNotifier, NotificationResult
from src.strategy.breakout import BreakoutSignal
from src.core.config import get_settings

logger = logging.getLogger(__name__)


class TelegramNotifier(BaseNotifier):
    """Telegram Bot API notifier using sendMessage."""

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        parse_mode: str = "Markdown",
        timeout: int = 10,
        enabled: bool = True,
    ):
        super().__init__("Telegram", enabled, timeout)
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.parse_mode = parse_mode
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    def _send_request(self, method: str, payload: dict) -> NotificationResult:
        """Send request to Telegram API."""
        url = f"{self.base_url}/{method}"
        try:
            response = requests.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            if data.get("ok"):
                return NotificationResult(True, "Message sent successfully")
            else:
                error = data.get("description", "Unknown error")
                return NotificationResult(False, "", f"Telegram API error: {error}")

        except requests.exceptions.Timeout:
            return NotificationResult(False, "", "Request timeout")
        except requests.exceptions.RequestException as e:
            return NotificationResult(False, "", f"Network error: {e}")

    def send_signal(self, signal: BreakoutSignal) -> NotificationResult:
        """Send formatted breakout signal to Telegram."""
        check = self._check_enabled()
        if check:
            return check

        if not signal.is_valid() or signal.levels is None:
            return NotificationResult(False, "", "Invalid signal")

        message = self._format_signal_message(signal)
        return self.send_message(message)

    def send_message(self, message: str) -> NotificationResult:
        """Send text message to Telegram chat."""
        check = self._check_enabled()
        if check:
            return check

        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": self.parse_mode,
            "disable_web_page_preview": True,
        }
        return self._send_request("sendMessage", payload)

    def test_connection(self) -> NotificationResult:
        """Test Telegram bot connection with getMe."""
        check = self._check_enabled()
        if check:
            return check

        try:
            response = requests.get(f"{self.base_url}/getMe", timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            if data.get("ok"):
                bot_info = data.get("result", {})
                bot_name = bot_info.get("first_name", "Unknown")
                bot_username = bot_info.get("username", "Unknown")
                return NotificationResult(
                    True,
                    f"Connected to @{bot_username} ({bot_name})"
                )
            else:
                return NotificationResult(False, "", f"API error: {data.get('description')}")

        except requests.exceptions.RequestException as e:
            return NotificationResult(False, "", f"Connection failed: {e}")

    def send_startup_message(self) -> NotificationResult:
        """Send bot startup notification."""
        message = (
            "🤖 **Signal Bot Started**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Monitoring for breakout signals...\n"
            "Use /status to check bot status."
        )
        return self.send_message(message)

    def send_shutdown_message(self) -> NotificationResult:
        """Send bot shutdown notification."""
        message = "🛑 **Signal Bot Stopped**"
        return self.send_message(message)


def create_telegram_notifier_from_config() -> Optional[TelegramNotifier]:
    """Create Telegram notifier from global config."""
    settings = get_settings()
    telegram_config = settings.notifications.telegram

    if not telegram_config.enabled:
        logger.info("Telegram notifications disabled in config")
        return None

    bot_token = settings.get_telegram_token()
    chat_id = settings.get_telegram_chat_id()

    if not bot_token or not chat_id:
        logger.warning("Telegram credentials not configured (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)")
        return None

    return TelegramNotifier(
        bot_token=bot_token,
        chat_id=chat_id,
        parse_mode=telegram_config.parse_mode,
        timeout=telegram_config.timeout,
        enabled=telegram_config.enabled,
    )