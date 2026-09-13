"""
Discord Webhook notification implementation with rich embeds.
"""
import logging
import time
import requests
from typing import Optional
from datetime import datetime

from src.notifications.base import BaseNotifier, NotificationResult
from src.strategy.breakout import BreakoutSignal
from src.strategy.levels import SignalSide
from src.core.config import get_settings

logger = logging.getLogger(__name__)


class DiscordNotifier(BaseNotifier):
    """Discord Webhook notifier with rich embed support."""

    def __init__(
        self,
        webhook_url: str,
        timeout: int = 10,
        embed_color_buy: int = 3066993,      # Green
        embed_color_sell: int = 15158332,    # Red
        embed_color_info: int = 3447003,     # Blue
        enabled: bool = True,
    ):
        super().__init__("Discord", enabled, timeout)
        self.webhook_url = webhook_url
        self.embed_color_buy = embed_color_buy
        self.embed_color_sell = embed_color_sell
        self.embed_color_info = embed_color_info

    def _send_webhook(self, payload: dict) -> NotificationResult:
        """Send payload to Discord webhook with rate limit handling."""
        max_retries = 3
        base_delay = 1.0

        for attempt in range(max_retries):
            try:
                response = requests.post(
                    self.webhook_url,
                    json=payload,
                    timeout=self.timeout,
                    headers={"Content-Type": "application/json"}
                )

                if response.status_code == 429:
                    # Rate limited - respect Retry-After header
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            delay = float(retry_after)
                        except ValueError:
                            delay = base_delay * (2 ** attempt)
                    else:
                        delay = base_delay * (2 ** attempt)

                    delay = min(delay, 60.0)  # Cap at 60 seconds
                    logger.warning(f"Discord rate limited (attempt {attempt + 1}/{max_retries}), waiting {delay:.1f}s")
                    time.sleep(delay)
                    continue

                response.raise_for_status()
                return NotificationResult(True, "Message sent successfully")

            except requests.exceptions.Timeout:
                if attempt == max_retries - 1:
                    return NotificationResult(False, "", "Request timeout after retries")
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Discord timeout (attempt {attempt + 1}/{max_retries}), retrying in {delay:.1f}s")
                time.sleep(delay)
            except requests.exceptions.HTTPError as e:
                if attempt == max_retries - 1:
                    return NotificationResult(False, "", f"HTTP error: {e}")
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Discord HTTP error (attempt {attempt + 1}/{max_retries}): {e}, retrying in {delay:.1f}s")
                time.sleep(delay)
            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:
                    return NotificationResult(False, "", f"Network error: {e}")
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Discord network error (attempt {attempt + 1}/{max_retries}): {e}, retrying in {delay:.1f}s")
                time.sleep(delay)

        return NotificationResult(False, "", "Max retries exceeded")

    def send_signal(self, signal: BreakoutSignal) -> NotificationResult:
        """Send breakout signal as rich embed to Discord."""
        check = self._check_enabled()
        if check:
            return check

        if not signal.is_valid() or signal.levels is None:
            return NotificationResult(False, "", "Invalid signal")

        levels = signal.levels
        is_buy = levels.side == SignalSide.BUY

        embed = {
            "title": f"{'🟢 BUY' if is_buy else '🔴 SELL'} Signal — {signal.symbol}",
            "color": self.embed_color_buy if is_buy else self.embed_color_sell,
            "timestamp": signal.timestamp.isoformat() if signal.timestamp else datetime.utcnow().isoformat(),
            "fields": [
                {
                    "name": "📈 Entry Price",
                    "value": f"`{levels.entry:.6f}`",
                    "inline": True
                },
                {
                    "name": "🛑 Stop Loss",
                    "value": f"`{levels.stop_loss:.6f}`",
                    "inline": True
                },
                {
                    "name": "🎯 Take Profit",
                    "value": f"`{levels.take_profit:.6f}`",
                    "inline": True
                },
                {
                    "name": "⚖️ R:R Ratio",
                    "value": f"`{levels.risk_reward_ratio:.2f}`",
                    "inline": True
                },
                {
                    "name": "📊 Timeframe",
                    "value": f"`{signal.timeframe}`",
                    "inline": True
                },
                {
                    "name": "🕐 Trigger Time",
                    "value": f"`{signal.timestamp.strftime('%H:%M:%S UTC') if signal.timestamp else 'N/A'}`",
                    "inline": True
                },
            ],
            "footer": {
                "text": "Signal Candle Jengat • Momentum Range Breakout"
            }
        }

        # Add trigger bar details
        embed["fields"].extend([
            {
                "name": "📍 Trigger Bar High",
                "value": f"`{levels.trigger_high:.6f}`",
                "inline": True
            },
            {
                "name": "📍 Trigger Bar Low",
                "value": f"`{levels.trigger_low:.6f}`",
                "inline": True
            },
            {
                "name": "📏 Range",
                "value": f"`{levels.trigger_range:.6f}`",
                "inline": True
            },
            {
                "name": "📊 ATR(14)",
                "value": f"`{levels.atr_value:.6f}`",
                "inline": True
            },
        ])

        payload = {
            "embeds": [embed],
            "username": "Signal Bot",
            "avatar_url": "https://cdn.discordapp.com/emojis/123456789.png"  # Optional
        }

        return self._send_webhook(payload)

    def send_message(self, message: str) -> NotificationResult:
        """Send simple text message to Discord."""
        check = self._check_enabled()
        if check:
            return check

        payload = {
            "content": message,
            "username": "Signal Bot"
        }
        return self._send_webhook(payload)

    def send_info_message(self, title: str, description: str, color: Optional[int] = None) -> NotificationResult:
        """Send info embed message."""
        check = self._check_enabled()
        if check:
            return check

        embed = {
            "title": title,
            "description": description,
            "color": color or self.embed_color_info,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": "Signal Candle Jengat"}
        }

        payload = {"embeds": [embed], "username": "Signal Bot"}
        return self._send_webhook(payload)

    def test_connection(self) -> NotificationResult:
        """Test Discord webhook with a simple message."""
        check = self._check_enabled()
        if check:
            return check

        embed = {
            "title": "🔧 Connection Test",
            "description": "Discord webhook connection successful!",
            "color": self.embed_color_info,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": "Signal Candle Jengat"}
        }

        payload = {"embeds": [embed], "username": "Signal Bot"}
        return self._send_webhook(payload)

    def send_startup_message(self) -> NotificationResult:
        """Send bot startup notification."""
        return self.send_info_message(
            "🤖 Signal Bot Started",
            "Monitoring for breakout signals...\nUse `/status` to check bot status."
        )

    def send_shutdown_message(self) -> NotificationResult:
        """Send bot shutdown notification."""
        return self.send_info_message(
            "🛑 Signal Bot Stopped",
            "Bot has been stopped.",
            color=self.embed_color_sell
        )

    def send_error_message(self, error: str, context: str = "") -> NotificationResult:
        """Send error notification."""
        description = f"**Error:** {error}"
        if context:
            description += f"\n**Context:** {context}"

        return self.send_info_message(
            "⚠️ Bot Error",
            description,
            color=self.embed_color_sell
        )


def create_discord_notifier_from_config(settings: Optional["Settings"] = None) -> Optional[DiscordNotifier]:
    """Create Discord notifier from global config."""
    from src.core.config import get_settings
    settings = settings or get_settings()
    discord_config = settings.notifications.discord

    if not discord_config.enabled:
        logger.info("Discord notifications disabled in config")
        return None

    webhook_url = settings.get_discord_webhook()

    if not webhook_url:
        logger.warning("Discord webhook URL not configured (DISCORD_WEBHOOK_URL)")
        return None

    return DiscordNotifier(
        webhook_url=webhook_url,
        timeout=discord_config.timeout,
        embed_color_buy=discord_config.embed_color_buy,
        embed_color_sell=discord_config.embed_color_sell,
        embed_color_info=discord_config.embed_color_info,
        enabled=discord_config.enabled,
    )