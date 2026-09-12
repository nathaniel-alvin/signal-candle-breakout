"""
Main bot orchestration - coordinates data fetching, strategy evaluation,
state management, and notifications.
"""
import logging
import signal
import sys
import time
from typing import Dict, List, Optional

from src.core.config import get_settings, Settings
from src.core.state import StateManager
from src.core.scheduler import CandleScheduler, create_scheduler_from_config
from src.data.fetcher import MarketDataFetcher, create_fetcher_from_config
from src.strategy.breakout import BreakoutStrategy, BreakoutSignal, SignalType, create_strategy_from_config
from src.notifications import NotificationManager, create_telegram_notifier_from_config, create_discord_notifier_from_config

logger = logging.getLogger(__name__)


class SignalBot:
    """Main signal bot orchestrator."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.running = False
        self._shutdown_requested = False

        # Initialize components
        self.state_manager = StateManager(
            persist_file=self.settings.state.persist_file,
            persist_enabled=self.settings.state.persist_enabled,
        )
        self.scheduler = create_scheduler_from_config()
        self.fetcher = create_fetcher_from_config()
        self.strategy = create_strategy_from_config()
        self.notification_manager = NotificationManager()

        # Setup notifiers
        self._setup_notifiers()

        # Register signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        logger.info("SignalBot initialized")

    def _setup_notifiers(self) -> None:
        """Initialize notification channels from config."""
        # Telegram
        telegram = create_telegram_notifier_from_config()
        if telegram:
            self.notification_manager.add_notifier(telegram)

        # Discord
        discord = create_discord_notifier_from_config()
        if discord:
            self.notification_manager.add_notifier(discord)

        if not self.notification_manager.notifiers:
            logger.warning("No notification channels configured!")

    def _signal_handler(self, signum, frame) -> None:
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        self._shutdown_requested = True

    def start(self) -> None:
        """Start the bot main loop."""
        self.running = True
        logger.info("=" * 50)
        logger.info("🚀 Signal Bot Starting")
        logger.info(f"Symbols: {self.settings.trading.symbols}")
        logger.info(f"Timeframe: {self.settings.trading.timeframe}")
        logger.info(f"Strategy: Momentum Range Breakout")
        logger.info("=" * 50)

        # Send startup notifications
        self._send_startup_notifications()

        try:
            self._main_loop()
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        except Exception as e:
            logger.exception(f"Fatal error in main loop: {e}")
            self._send_error_notification(str(e))
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop the bot gracefully."""
        if not self.running:
            return

        self.running = False
        logger.info("🛑 Signal Bot Stopping...")

        # Send shutdown notifications
        self._send_shutdown_notifications()

        # Cleanup
        self.fetcher.close()
        logger.info("Signal Bot stopped")

    def _main_loop(self) -> None:
        """Main polling loop."""
        while self.running and not self._shutdown_requested:
            loop_start = time.time()

            try:
                # Process each symbol
                for symbol in self.settings.trading.symbols:
                    if self._shutdown_requested:
                        break
                    self._process_symbol(symbol)

            except Exception as e:
                logger.error(f"Error in main loop iteration: {e}")
                self._send_error_notification(f"Main loop error: {e}")

            # Sleep until next candle
            if self.running and not self._shutdown_requested:
                self.scheduler.sleep_until_next_candle()

    def _process_symbol(self, symbol: str) -> None:
        """Process a single symbol: fetch data, evaluate strategy, send signals."""
        logger.debug(f"Processing {symbol}...")

        try:
            # Fetch market data
            df = self.fetcher.fetch_ohlcv_df(
                symbol=symbol,
                timeframe=self.settings.trading.timeframe,
                limit=self.settings.trading.fetch_limit,
            )

            if df.empty:
                logger.warning(f"No data received for {symbol}")
                return

            # Get latest complete candle timestamp
            latest_complete = df.iloc[-2]
            candle_timestamp = int(latest_complete.name.timestamp() * 1000)  # ms

            # Check if we already processed this candle
            if not self.state_manager.is_new_candle(symbol, candle_timestamp):
                logger.debug(f"Candle already processed for {symbol}")
                return

            # Check for active trade (prevent consecutive signals)
            if self.settings.state.prevent_consecutive_signals:
                active_trade = self.state_manager.get_active_trade(symbol)
                if active_trade:
                    # Check if active trade hit TP/SL
                    current_price = float(df.iloc[-1]["close"])  # forming candle close
                    exit_reason = self.state_manager.check_and_clear_active_trade(symbol, current_price)
                    if exit_reason:
                        logger.info(f"Active trade for {symbol} closed: {exit_reason}")
                        self._send_trade_exit_notification(symbol, active_trade, exit_reason, current_price)
                    else:
                        logger.debug(f"Active trade exists for {symbol}, skipping new signal")
                        return

            # Evaluate strategy
            signal = self.strategy.evaluate(df, symbol, self.settings.trading.timeframe)

            if signal.is_valid() and signal.levels:
                # New signal generated!
                logger.info(f"✅ New {signal.signal_type.value} signal for {symbol}")

                # Update state
                self.state_manager.update_candle_state(
                    symbol=symbol,
                    timestamp=candle_timestamp,
                    close_price=float(latest_complete["close"]),
                )

                # Record active trade
                if self.settings.state.track_active_trades:
                    self.state_manager.set_active_trade(
                        symbol=symbol,
                        side=signal.levels.side.value,
                        entry_price=signal.levels.entry,
                        stop_loss=signal.levels.stop_loss,
                        take_profit=signal.levels.take_profit,
                        trigger_candle_timestamp=candle_timestamp,
                        trigger_high=signal.levels.trigger_high,
                        trigger_low=signal.levels.trigger_low,
                    )

                # Send notifications
                self.notification_manager.send_signal(signal)

            else:
                # No signal, still update candle state to prevent re-processing
                self.state_manager.update_candle_state(
                    symbol=symbol,
                    timestamp=candle_timestamp,
                    close_price=float(latest_complete["close"]),
                )
                logger.debug(f"No signal for {symbol}")

        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}")

    def _send_startup_notifications(self) -> None:
        """Send startup notifications to all channels."""
        message = (
            "🤖 **Signal Bot Started**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"**Symbols:** {', '.join(self.settings.trading.symbols)}\n"
            f"**Timeframe:** {self.settings.trading.timeframe}\n"
            f"**Strategy:** Momentum Range Breakout\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Monitoring for breakout signals..."
        )
        self.notification_manager.send_message(message)

    def _send_shutdown_notifications(self) -> None:
        """Send shutdown notifications."""
        message = "🛑 **Signal Bot Stopped**"
        self.notification_manager.send_message(message)

    def _send_error_notification(self, error: str) -> None:
        """Send error notification."""
        message = f"⚠️ **Bot Error**\n```\n{error}\n```"
        self.notification_manager.send_message(message)

    def _send_trade_exit_notification(
        self,
        symbol: str,
        trade,
        exit_reason: str,
        exit_price: float
    ) -> None:
        """Send trade exit notification."""
        emoji = "✅" if exit_reason == "TP" else "❌"
        side_emoji = "🟢" if trade.side == "BUY" else "🔴"

        message = (
            f"{emoji} **Trade Closed: {exit_reason}**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"{side_emoji} {trade.side} {symbol}\n"
            f"Entry: `{trade.entry_price:.6f}`\n"
            f"Exit: `{exit_price:.6f}`\n"
            f"SL: `{trade.stop_loss:.6f}` | TP: `{trade.take_profit:.6f}`\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        self.notification_manager.send_message(message)

    def run_once(self) -> Dict[str, BreakoutSignal]:
        """Run a single iteration for all symbols (for testing)."""
        results = {}
        for symbol in self.settings.trading.symbols:
            try:
                df = self.fetcher.fetch_ohlcv_df(
                    symbol=symbol,
                    timeframe=self.settings.trading.timeframe,
                    limit=self.settings.trading.fetch_limit,
                )
                if not df.empty:
                    signal = self.strategy.evaluate(df, symbol, self.settings.trading.timeframe)
                    results[symbol] = signal
            except Exception as e:
                logger.error(f"Error in run_once for {symbol}: {e}")
                results[symbol] = None
        return results


def create_bot() -> SignalBot:
    """Factory function to create bot instance."""
    return SignalBot()


def main() -> None:
    """Entry point for running the bot."""
    bot = create_bot()
    bot.start()


if __name__ == "__main__":
    main()