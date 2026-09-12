"""
Technical indicators for the breakout strategy.
"""
import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def calculate_candle_ranges(df: pd.DataFrame) -> pd.Series:
    """
    Calculate full candle range (High - Low) for each candle.

    Args:
        df: DataFrame with 'high' and 'low' columns

    Returns:
        Series of candle ranges
    """
    return df["high"] - df["low"]


def calculate_real_body(df: pd.DataFrame) -> pd.Series:
    """
    Calculate real body size (abs(Close - Open)) for each candle.

    Args:
        df: DataFrame with 'open' and 'close' columns

    Returns:
        Series of real body sizes
    """
    return (df["close"] - df["open"]).abs()


def calculate_body_ratio(df: pd.DataFrame) -> pd.Series:
    """
    Calculate real body as percentage of full candle range.

    Args:
        df: DataFrame with OHLC columns

    Returns:
        Series of body ratios (0 to 1+)
    """
    ranges = calculate_candle_ranges(df)
    bodies = calculate_real_body(df)
    # Avoid division by zero
    return np.where(ranges > 0, bodies / ranges, 0)


def sma(series: pd.Series, period: int) -> pd.Series:
    """
    Simple Moving Average.

    Args:
        series: Input series
        period: Lookback period

    Returns:
        SMA series
    """
    return series.rolling(window=period, min_periods=period).mean()


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Average True Range (Wilder's smoothing).

    Args:
        df: DataFrame with 'high', 'low', 'close' columns
        period: ATR period (default 14)

    Returns:
        ATR series
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]

    # True Range components
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Wilder's smoothing (EMA with alpha = 1/period)
    atr_series = true_range.ewm(alpha=1/period, adjust=False, min_periods=period).mean()

    return atr_series


def range_sma(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    SMA of candle ranges over specified period.

    Args:
        df: DataFrame with 'high', 'low' columns
        period: Lookback period

    Returns:
        SMA of ranges
    """
    ranges = calculate_candle_ranges(df)
    return sma(ranges, period)


def highest_high(df: pd.DataFrame, period: int, shift: int = 1) -> pd.Series:
    """
    Highest high over lookback period, shifted.

    Args:
        df: DataFrame with 'high' column
        period: Lookback period
        shift: Number of periods to shift (default 1 for previous candles)

    Returns:
        Series of highest highs
    """
    return df["high"].rolling(window=period, min_periods=period).max().shift(shift)


def lowest_low(df: pd.DataFrame, period: int, shift: int = 1) -> pd.Series:
    """
    Lowest low over lookback period, shifted.

    Args:
        df: DataFrame with 'low' column
        period: Lookback period
        shift: Number of periods to shift (default 1 for previous candles)

    Returns:
        Series of lowest lows
    """
    return df["low"].rolling(window=period, min_periods=period).min().shift(shift)


def add_indicators(
    df: pd.DataFrame,
    atr_period: int = 14,
    range_sma_period: int = 14,
    breakout_lookback: int = 20,
) -> pd.DataFrame:
    """
    Add all required indicators to DataFrame.

    Args:
        df: DataFrame with OHLCV columns
        atr_period: ATR period
        range_sma_period: Range SMA period
        breakout_lookback: Breakout lookback period

    Returns:
        DataFrame with added indicator columns
    """
    df = df.copy()

    # Candle properties
    df["range"] = calculate_candle_ranges(df)
    df["body"] = calculate_real_body(df)
    df["body_ratio"] = calculate_body_ratio(df)
    df["is_bullish"] = df["close"] > df["open"]
    df["is_bearish"] = df["close"] < df["open"]

    # Indicators
    df["atr"] = atr(df, atr_period)
    df["range_sma"] = range_sma(df, range_sma_period)
    df["highest_high"] = highest_high(df, breakout_lookback, shift=1)
    df["lowest_low"] = lowest_low(df, breakout_lookback, shift=1)

    # Volatility expansion: range >= multiplier * range_sma
    df["volatility_expanded"] = df["range"] >= df["range_sma"]

    # Breakout conditions
    df["breakout_up"] = df["close"] > df["highest_high"]
    df["breakout_down"] = df["close"] < df["lowest_low"]

    return df


def get_latest_complete_candle(df: pd.DataFrame) -> pd.Series:
    """
    Get the latest COMPLETE (closed) candle.
    Uses iloc[-2] since iloc[-1] is the currently forming candle.

    Args:
        df: DataFrame with datetime index

    Returns:
        Series of the latest complete candle

    Raises:
        ValueError: If not enough candles
    """
    if len(df) < 2:
        raise ValueError("Need at least 2 candles (1 complete + 1 forming)")
    return df.iloc[-2]


def get_latest_forming_candle(df: pd.DataFrame) -> pd.Series:
    """
    Get the currently forming (incomplete) candle.

    Args:
        df: DataFrame with datetime index

    Returns:
        Series of the latest forming candle
    """
    return df.iloc[-1]


def validate_dataframe(df: pd.DataFrame, min_rows: int = 35) -> bool:
    """
    Validate DataFrame has required columns and minimum rows.

    Args:
        df: DataFrame to validate
        min_rows: Minimum required rows (for indicators + lookback)

    Returns:
        True if valid

    Raises:
        ValueError: If validation fails
    """
    required_columns = {"open", "high", "low", "close", "volume"}
    missing = required_columns - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    if len(df) < min_rows:
        raise ValueError(
            f"Insufficient data: {len(df)} rows, need at least {min_rows} "
            f"for indicators (ATR={14}, Range SMA={14}, Breakout={20})"
        )

    if df.isnull().any().any():
        raise ValueError("DataFrame contains NaN values")

    return True