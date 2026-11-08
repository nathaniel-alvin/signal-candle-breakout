#!/usr/bin/env python3
"""
Signal Candle Jengat - Real-time Crypto Breakout Signal Bot
Entry point for running the bot or backtests.
"""
import argparse
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.core.config import get_settings, reload_settings
from src.core.logging_setup import setup_logging
from src.bot import SignalBot, create_bot
# from src.backtest.engine import run_backtest_from_config


def parse_args():
    parser = argparse.ArgumentParser(
        description="Signal Candle Jengat - Crypto Breakout Signal Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                    # Run live bot
  python main.py --backtest         # Run backtest on all configured symbols
  python main.py --backtest BTC/USDT ETH/USDT  # Backtest specific symbols
  python main.py --once             # Run single iteration (testing)
  python main.py --config custom.yaml  # Use custom config file
  python main.py --test-notifications  # Test notification channels
        """
    )

    parser.add_argument(
        "--config", "-c",
        type=str,
        default="config/settings.yaml",
        help="Path to config YAML file (default: config/settings.yaml)"
    )

    parser.add_argument(
        "--backtest", "-b",
        nargs="*",
        metavar="SYMBOL",
        help="Run backtest. Optionally specify symbols (default: all from config)"
    )

    parser.add_argument(
        "--timeframe", "-t",
        type=str,
        help="Timeframe for backtest (default: from config)"
    )

    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=500,
        help="Number of candles for backtest (default: 500)"
    )

    parser.add_argument(
        "--once", "-o",
        action="store_true",
        help="Run single iteration and exit (for testing)"
    )

    parser.add_argument(
        "--test-notifications",
        action="store_true",
        help="Test notification channels and exit"
    )

    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Override log level"
    )

    return parser.parse_args()


def run_live_bot(config_path: str, log_level: str = None, run_once: bool = False):
    """Run the live signal bot."""
    # Load settings
    settings = get_settings(config_path)
    if log_level:
        settings.logging.level = log_level

    # Setup logging
    setup_logging(settings)

    logger = logging.getLogger(__name__)
    logger.info("Starting Signal Candle Jengat...")

    # Create and start bot
    bot = create_bot()

    if run_once:
        logger.info("Running single iteration...")
        results = bot.run_once()
        for symbol, tf_results in results.items():
            for timeframe, signal in tf_results.items():
                if signal and signal.is_valid():
                    print(f"\n{symbol} [{timeframe}]: {signal.signal_type.value}")
                    print(signal.levels.format_for_message())
                else:
                    print(f"\n{symbol} [{timeframe}]: No signal")
        bot.stop()
    else:
        bot.start()


# def run_backtest(config_path: str, symbols: list = None, timeframe: str = None,
#                  limit: int = 500, log_level: str = None):
#     """Run backtest."""
#     settings = get_settings(config_path)
#     if log_level:
#         settings.logging.level = log_level
#
#     setup_logging(settings)
#
#     logger = logging.getLogger(__name__)
#     logger.info("Running backtest...")
#
#     results = run_backtest_from_config(
#         symbols=symbols,
#         timeframe=timeframe,
#         limit=limit,
#     )
#
#     # Print combined summary
#     print("\n" + "=" * 60)
#     print("COMBINED BACKTEST SUMMARY")
#     print("=" * 60)
#     for symbol, result in results.items():
#         if result:
#             print(f"\n{symbol}:")
#             print(f"  Trades: {result.total_trades} | Win Rate: {result.win_rate:.1f}% | "
#                   f"Total P&L: {result.total_pnl_pct:.2f}% | PF: {result.profit_factor:.2f}")
#         else:
#             print(f"\n{symbol}: FAILED")
#
#     return results


def test_notifications(config_path: str, log_level: str = None):
    """Test notification channels."""
    settings = get_settings(config_path)
    if log_level:
        settings.logging.level = log_level

    setup_logging(settings)

    logger = logging.getLogger(__name__)
    logger.info("Testing notification channels...")

    bot = create_bot()

    if bot.notification_manager.notifiers:
        print("\nTesting notifiers...")
        results = bot.notification_manager.test_all()
        for result in results:
            status = "✅" if result.success else "❌"
            print(f"  {status} {result.message or result.error}")
    else:
        print("No notifiers configured!")


def main():
    args = parse_args()

    # Validate config exists
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"❌ Config file not found: {config_path}")
        print(f"   Copy config/settings.yaml.example to config/settings.yaml and configure it")
        sys.exit(1)

    try:
        # if args.backtest is not None:
        #     # Backtest mode (symbols optional)
        #     symbols = args.backtest if args.backtest else None
        #     run_backtest(
        #         config_path=str(config_path),
        #         symbols=symbols,
        #         timeframe=args.timeframe,
        #         limit=args.limit,
        #         log_level=args.log_level,
        #     )

        if args.test_notifications:
            test_notifications(str(config_path), args.log_level)

        elif args.once:
            run_live_bot(str(config_path), args.log_level, run_once=True)

        else:
            # Live bot mode
            run_live_bot(str(config_path), args.log_level, run_once=False)

    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
