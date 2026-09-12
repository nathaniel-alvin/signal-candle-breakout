"""
Momentum Range Breakout Strategy Implementation.

Signal triggers only on the close of a candle that satisfies all four conditions:
1. Strong Body: Real body >= 75% of full candle range
2. Directional Match: Bullish for BUY, Bearish for SELL
3. Volatility Expansion: Candle range >= 1.2x 14-period SMA of ranges
4. Base Breakout: Close breaks above 20-candle high (BUY) or below 20-candle low (SELL)
"""
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

import pandas as pd

from src.data.indicators import add_indicators, get_latest_complete_candle, validate_dataframe
from src.strategy.levels import SignalSide, ExecutionLevels, calculate_levels, validate_levels
from src.core.config import get_settings

logger = logging.getLogger(__name__)


class SignalType(Enum):
    NONE = "NONE"
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class BreakoutSignal:
    """Breakout signal with all relevant data."""
    symbol: str
    timeframe: str
    signal_type: SignalType
    candle: pd.Series
    levels: Optional[ExecutionLevels] = None
    timestamp: Optional[pd.Timestamp] = None

    def is_valid(self) -> bool:
        return self.signal_type != SignalType.NONE and self.levels is not None


class BreakoutStrategy:
    """Momentum Range Breakout strategy evaluator."""

    def __init__(
        self,
        strong_body_pct: float = 0.75,
        volatility_multiplier: float = 1.2,
        breakout_lookback: int = 20,
        atr_period: int = 14,
        range_sma_period: int = 14,
        entry_retrace: float = 0.236,
        sl_atr_multiplier: float = 0.10,
        tp_extension: float = 0.27,
        min_rr_ratio: float = 1.0,
    ):
        self.strong_body_pct = strong_body_pct
        self.volatility_multiplier = volatility_multiplier
        self.breakout_lookback = breakout_lookback
        self.atr_period = atr_period
        self.range_sma_period = range_sma_period
        self.entry_retrace = entry_retrace
        self.sl_atr_multiplier = sl_atr_multiplier
        self.tp_extension = tp_extension
        self.min_rr_ratio = min_rr_ratio

        logger.info(
            f"BreakoutStrategy initialized: "
            f"body>={strong_body_pct*100:.0f}%, "
            f"vol_mult>={volatility_multiplier}, "
            f"lookback={breakout_lookback}, "
            f"atr={atr_period}, "
            f"range_sma={range_sma_period}"
        )

    def evaluate(self, df: pd.DataFrame, symbol: str, timeframe: str) -> BreakoutSignal:
        """
        Evaluate strategy on latest complete candle.

        Args:
            df: DataFrame with OHLCV data (must have enough history for indicators)
            symbol: Trading pair symbol
            timeframe: Candle timeframe

        Returns:
            BreakoutSignal with signal type and levels if triggered
        """
        # Validate input data
        try:
            validate_dataframe(df, min_rows=max(self.atr_period, self.range_sma_period, self.breakout_lookback) + 5)
        except ValueError as e:
            logger.warning(f"Data validation failed for {symbol}: {e}")
            return BreakoutSignal(symbol, timeframe, SignalType.NONE, pd.Series())

        # Add indicators
        df = add_indicators(
            df,
            atr_period=self.atr_period,
            range_sma_period=self.range_sma_period,
            breakout_lookback=self.breakout_lookback,
        )

        # Get latest COMPLETE candle (iloc[-2], not iloc[-1])
        try:
            candle = get_latest_complete_candle(df)
        except ValueError as e:
            logger.warning(f"Cannot get complete candle for {symbol}: {e}")
            return BreakoutSignal(symbol, timeframe, SignalType.NONE, pd.Series())

        # Get indicator values from the complete candle
        body_ratio = candle["body_ratio"]
        is_bullish = candle["is_bullish"]
        is_bearish = candle["is_bearish"]
        volatility_expanded = candle["volatility_expanded"]
        breakout_up = candle["breakout_up"]
        breakout_down = candle["breakout_down"]
        atr_value = candle["atr"]
        range_sma = candle["range_sma"]
        highest_high = candle["highest_high"]
        lowest_low = candle["lowest_low"]

        # Check for NaN in critical indicators
        critical_indicators = {
            "body_ratio": body_ratio,
            "atr": atr_value,
            "range_sma": range_sma,
            "highest_high": highest_high,
            "lowest_low": lowest_low,
        }

        if any(pd.isna(v) for v in critical_indicators.values()):
            logger.debug(f"Indicators not ready for {symbol} (NaN values)")
            return BreakoutSignal(symbol, timeframe, SignalType.NONE, candle)

        # ============================================
        # EVALUATE FOUR CONDITIONS
        # ============================================

        # Condition 1: Strong Body
        cond_strong_body = body_ratio >= self.strong_body_pct

        # Condition 2: Directional Match
        cond_bullish = is_bullish
        cond_bearish = is_bearish

        # Condition 3: Volatility Expansion
        cond_vol_expansion = (
            volatility_expanded and
            candle["range"] >= (self.volatility_multiplier * range_sma)
        )

        # Condition 4: Base Breakout
        cond_breakout_up = breakout_up
        cond_breakout_down = breakout_down

        # Log condition states for debugging
        logger.debug(
            f"{symbol} Conditions: "
            f"Body={body_ratio:.3f}(>={self.strong_body_pct}) "
            f"Bull={cond_bullish} Bear={cond_bearish} "
            f"VolExp={cond_vol_expansion}(range={candle['range']:.6f} vs {self.volatility_multiplier}*{range_sma:.6f}) "
            f"BreakUp={cond_breakout_up}(close={candle['close']:.6f} > HH={highest_high:.6f}) "
            f"BreakDown={cond_breakout_down}(close={candle['close']:.6f} < LL={lowest_low:.6f})"
        )

        # ============================================
        # DETERMINE SIGNAL
        # ============================================

        signal_type = SignalType.NONE
        levels = None

        # BUY Signal: All conditions met for bullish breakout
        if (cond_strong_body and cond_bullish and cond_vol_expansion and cond_breakout_up):
            signal_type = SignalType.BUY
            levels = calculate_levels(
                candle=candle,
                atr_value=atr_value,
                side=SignalSide.BUY,
                entry_retrace=self.entry_retrace,
                sl_atr_multiplier=self.sl_atr_multiplier,
                tp_extension=self.tp_extension,
            )
            # Validate R:R
            if not validate_levels(levels, self.min_rr_ratio):
                logger.warning(f"{symbol} BUY signal rejected: R:R {levels.risk_reward_ratio:.2f} < {self.min_rr_ratio}")
                signal_type = SignalType.NONE
                levels = None

        # SELL Signal: All conditions met for bearish breakout
        elif (cond_strong_body and cond_bearish and cond_vol_expansion and cond_breakout_down):
            signal_type = SignalType.SELL
            levels = calculate_levels(
                candle=candle,
                atr_value=atr_value,
                side=SignalSide.SELL,
                entry_retrace=self.entry_retrace,
                sl_atr_multiplier=self.sl_atr_multiplier,
                tp_extension=self.tp_extension,
            )
            # Validate R:R
            if not validate_levels(levels, self.min_rr_ratio):
                logger.warning(f"{symbol} SELL signal rejected: R:R {levels.risk_reward_ratio:.2f} < {self.min_rr_ratio}")
                signal_type = SignalType.NONE
                levels = None

        if signal_type != SignalType.NONE:
            logger.info(
                f"🚀 {signal_type.value} SIGNAL for {symbol} {timeframe} @ "
                f"{candle.name}: Entry={levels.entry:.6f}, "
                f"SL={levels.stop_loss:.6f}, TP={levels.take_profit:.6f}, "
                f"R:R={levels.risk_reward_ratio:.2f}"
            )

        return BreakoutSignal(
            symbol=symbol,
            timeframe=timeframe,
            signal_type=signal_type,
            candle=candle,
            levels=levels,
            timestamp=candle.name,
        )

    def evaluate_all_candles(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Evaluate strategy on ALL candles (for backtesting).

        Args:
            df: DataFrame with OHLCV data

        Returns:
            DataFrame with signal columns added
        """
        df = add_indicators(
            df,
            atr_period=self.atr_period,
            range_sma_period=self.range_sma_period,
            breakout_lookback=self.breakout_lookback,
        )

        # Initialize signal columns
        df["signal"] = SignalType.NONE.value
        df["entry"] = None
        df["stop_loss"] = None
        df["take_profit"] = None
        df["rr_ratio"] = None

        # Evaluate each candle (starting from where indicators are ready)
        start_idx = max(self.atr_period, self.range_sma_period, self.breakout_lookback)

        for i in range(start_idx, len(df)):
            candle = df.iloc[i]

            # Skip if indicators not ready
            if any(pd.isna(candle[col]) for col in ["atr", "range_sma", "highest_high", "lowest_low"]):
                continue

            body_ratio = candle["body_ratio"]
            is_bullish = candle["is_bullish"]
            is_bearish = candle["is_bearish"]
            vol_expanded = (
                candle["volatility_expanded"] and
                candle["range"] >= (self.volatility_multiplier * candle["range_sma"])
            )
            breakout_up = candle["breakout_up"]
            breakout_down = candle["breakout_down"]

            cond_strong_body = body_ratio >= self.strong_body_pct

            if (cond_strong_body and is_bullish and vol_expanded and breakout_up):
                levels = calculate_levels(
                    candle=candle,
                    atr_value=candle["atr"],
                    side=SignalSide.BUY,
                    entry_retrace=self.entry_retrace,
                    sl_atr_multiplier=self.sl_atr_multiplier,
                    tp_extension=self.tp_extension,
                )
                if validate_levels(levels, self.min_rr_ratio):
                    df.at[df.index[i], "signal"] = SignalType.BUY.value
                    df.at[df.index[i], "entry"] = levels.entry
                    df.at[df.index[i], "stop_loss"] = levels.stop_loss
                    df.at[df.index[i], "take_profit"] = levels.take_profit
                    df.at[df.index[i], "rr_ratio"] = levels.risk_reward_ratio

            elif (cond_strong_body and is_bearish and vol_expanded and breakout_down):
                levels = calculate_levels(
                    candle=candle,
                    atr_value=candle["atr"],
                    side=SignalSide.SELL,
                    entry_retrace=self.entry_retrace,
                    sl_atr_multiplier=self.sl_atr_multiplier,
                    tp_extension=self.tp_extension,
                )
                if validate_levels(levels, self.min_rr_ratio):
                    df.at[df.index[i], "signal"] = SignalType.SELL.value
                    df.at[df.index[i], "entry"] = levels.entry
                    df.at[df.index[i], "stop_loss"] = levels.stop_loss
                    df.at[df.index[i], "take_profit"] = levels.take_profit
                    df.at[df.index[i], "rr_ratio"] = levels.risk_reward_ratio

        return df


def create_strategy_from_config() -> BreakoutStrategy:
    """Create strategy from global config."""
    settings = get_settings()
    return BreakoutStrategy(
        strong_body_pct=settings.strategy.strong_body_pct,
        volatility_multiplier=settings.strategy.volatility_multiplier,
        breakout_lookback=settings.strategy.breakout_lookback,
        atr_period=settings.strategy.atr_period,
        range_sma_period=settings.strategy.range_sma_period,
        entry_retrace=settings.fibonacci.entry_retrace,
        sl_atr_multiplier=settings.fibonacci.sl_atr_multiplier,
        tp_extension=settings.fibonacci.tp_extension,
    )