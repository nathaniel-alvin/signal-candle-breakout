"""
Main bot orchestration - coordinates data fetching, strategy evaluation,
state management, and notifications.
"""
import logging
import signal
import sys
import time
from typing import Dict, List, Optional, Set, Tuple

from src.core.config import get_settings, Settings
from src.core.state import StateManager
from src.core.scheduler import CandleScheduler, MultiTimeframeScheduler, create_scheduler_from_config
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
            settings=self.settings,
        )
        # Multi-timeframe scheduler
        self.multi_scheduler = MultiTimeframeScheduler(
            timeframes=self.settings.trading.timeframes,
            buffer_seconds=self.settings.scheduler.buffer_seconds,
            max_sleep_seconds=self.settings.scheduler.max_sleep_seconds,
            timezone_str=self.settings.scheduler.timezone,
        )
        # Keep single scheduler for backward compat (e.g., run_once)
        self.scheduler = create_scheduler_from_config(settings=self.settings)
        self.fetcher = create_fetcher_from_config(settings=self.settings)
        self.strategy = create_strategy_from_config(settings=self.settings)
        self.notification_manager = NotificationManager()

        # Per-(symbol, timeframe) circuit breaker: track consecutive failures
        self._tf_failures: Dict[Tuple[str, str], int] = {}
        self._disabled_tfs: Set[Tuple[str, str]] = set()

        # Setup notifiers
        self._setup_notifiers()

        # Register signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        logger.info("SignalBot initialized")

    def _setup_notifiers(self) -> None:
        """Initialize notification channels from config."""
        # Telegram
        telegram = create_telegram_notifier_from_config(settings=self.settings)
        if telegram:
            self.notification_manager.add_notifier(telegram)

        # Discord
        discord = create_discord_notifier_from_config(settings=self.settings)
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
        logger.info(f"Timeframes: {self.settings.trading.timeframes}")
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
        """Main polling loop - multi-timeframe aware."""
        while self.running and not self._shutdown_requested:
            try:
                # Sleep until the earliest next candle close across all timeframes
                ready_timeframes = self.multi_scheduler.sleep_until_next_any(
                    shutdown_check=lambda: self._shutdown_requested
                )

                if self._shutdown_requested:
                    break

                # Process symbols for each ready timeframe
                for tf in ready_timeframes:
                    if self._shutdown_requested:
                        break
                    for symbol in self.settings.trading.symbols:
                        if self._shutdown_requested:
                            break
                        self._process_symbol(symbol, tf)

            except Exception as e:
                logger.error(f"Error in main loop iteration: {e}")
                self._send_error_notification(f"Main loop error: {e}")

    def _process_symbol(self, symbol: str, timeframe: str) -> None:
        """Process a single symbol for a specific timeframe: fetch data, evaluate strategy, send signals."""
        # Skip disabled (symbol, timeframe) pairs
        tf_key = (symbol, timeframe)
        if tf_key in self._disabled_tfs:
            logger.debug(f"Skipping disabled symbol/timeframe: {symbol} [{timeframe}]")
            return

        logger.debug(f"Processing {symbol} [{timeframe}]...")

        try:
            # Fetch market data with freshness check
            df = self.fetcher.fetch_ohlcv_df(
                symbol=symbol,
                timeframe=timeframe,
                limit=self.settings.trading.fetch_limit,
                max_candle_age_seconds=self.settings.max_candle_age_seconds,
            )

            if df.empty:
                logger.warning(f"No data received for {symbol} [{timeframe}]")
                self._record_failure(symbol, timeframe)
                return

            # Get latest complete candle timestamp
            latest_complete = df.iloc[-2]
            candle_timestamp = int(latest_complete.name.timestamp() * 1000)  # ms

            # Check if we already processed this candle
            if not self.state_manager.is_new_candle(symbol, timeframe, candle_timestamp):
                logger.debug(f"Candle already processed for {symbol} [{timeframe}]")
                return

            # Check for active trade (prevent consecutive signals)
            if self.settings.state.prevent_consecutive_signals:
                active_trade = self.state_manager.get_active_trade(symbol, timeframe)
                if active_trade:
                    # Check if active trade hit TP/SL
                    current_price = float(df.iloc[-1]["close"])  # forming candle close
                    exit_reason = self.state_manager.check_and_clear_active_trade(symbol, timeframe, current_price)
                    if exit_reason:
                        logger.info(f"Active trade for {symbol} [{timeframe}] closed: {exit_reason}")
                        self._send_trade_exit_notification(symbol, active_trade, exit_reason, current_price)
                    else:
                        logger.debug(f"Active trade exists for {symbol} [{timeframe}], skipping new signal")
                        return

            # Evaluate strategy
            signal = self.strategy.evaluate(df, symbol, timeframe)

            if signal.is_valid() and signal.levels:
                # New signal generated!
                logger.info(f"✅ New {signal.signal_type.value} signal for {symbol} [{timeframe}]")

                # Update state
                self.state_manager.update_candle_state(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=candle_timestamp,
                    close_price=float(latest_complete["close"]),
                )

                # Record active trade
                if self.settings.state.track_active_trades:
                    self.state_manager.set_active_trade(
                        symbol=symbol,
                        timeframe=timeframe,
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
                    timeframe=timeframe,
                    timestamp=candle_timestamp,
                    close_price=float(latest_complete["close"]),
                )
                logger.debug(f"No signal for {symbol} [{timeframe}]")

            # Success - reset failure counter
            self._record_success(symbol, timeframe)

        except Exception as e:
            logger.error(f"Error processing {symbol} [{timeframe}]: {e}")
            self._record_failure(symbol, timeframe)

    def _record_success(self, symbol: str, timeframe: str) -> None:
        """Reset failure counter on successful processing."""
        tf_key = (symbol, timeframe)
        if self._tf_failures.get(tf_key, 0) > 0:
            logger.debug(f"Symbol {symbol} [{timeframe}] recovered after {self._tf_failures[tf_key]} failures")
        self._tf_failures[tf_key] = 0

    def _record_failure(self, symbol: str, timeframe: str) -> None:
        """Track consecutive failures; disable symbol/timeframe if threshold exceeded."""
        tf_key = (symbol, timeframe)
        self._tf_failures[tf_key] = self._tf_failures.get(tf_key, 0) + 1
        failures = self._tf_failures[tf_key]
        logger.warning(f"Symbol {symbol} [{timeframe}] failure #{failures}")

        if failures >= self.settings.max_consecutive_failures:
            self._disabled_tfs.add(tf_key)
            logger.error(
                f"Symbol {symbol} [{timeframe}] disabled after {failures} consecutive failures. "
                f"Max allowed: {self.settings.max_consecutive_failures}. "
                f"Restart bot or reload config to re-enable."
            )
            # Send notification about disabled symbol/timeframe
            self.notification_manager.send_message(
                f"⚠️ **Symbol/Timeframe Disabled**\n"
                f"`{symbol}` [{timeframe}] disabled after {failures} consecutive failures. "
                f"Check logs and restart to re-enable."
            )

    def _send_startup_notifications(self) -> None:
        """Send startup notifications to all channels."""
        message = (
            "🤖 **Signal Bot Started**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"**Symbols:** {', '.join(self.settings.trading.symbols)}\n"
            f"**Timeframes:** {', '.join(self.settings.trading.timeframes)}\n"
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

    def run_once(self) -> Dict[str, Dict[str, BreakoutSignal]]:
        """Run a single iteration for all symbols and timeframes (for testing)."""
        results = {}
        for symbol in self.settings.trading.symbols:
            results[symbol] = {}
            for timeframe in self.settings.trading.timeframes:
                try:
                    df = self.fetcher.fetch_ohlcv_df(
                        symbol=symbol,
                        timeframe=timeframe,
                        limit=self.settings.trading.fetch_limit,
                        max_candle_age_seconds=self.settings.max_candle_age_seconds,
                    )
                    if not df.empty:
                        signal = self.strategy.evaluate(df, symbol, timeframe)
                        results[symbol][timeframe] = signal
                    else:
                        results[symbol][timeframe] = None
                except Exception as e:
                    logger.error(f"Error in run_once for {symbol} [{timeframe}]: {e}")
                    results[symbol][timeframe] = None
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