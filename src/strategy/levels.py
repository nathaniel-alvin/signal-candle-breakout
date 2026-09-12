"""
Fibonacci-based execution level calculations (Entry, SL, TP) and R:R ratio.
"""
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd

from src.core.config import get_settings

logger = logging.getLogger(__name__)


class SignalSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class ExecutionLevels:
    """Calculated execution levels for a trade."""
    side: SignalSide
    entry: float
    stop_loss: float
    take_profit: float
    risk_reward_ratio: float
    trigger_high: float
    trigger_low: float
    trigger_range: float
    atr_value: float

    def to_dict(self) -> dict:
        return {
            "side": self.side.value,
            "entry": round(self.entry, 6),
            "stop_loss": round(self.stop_loss, 6),
            "take_profit": round(self.take_profit, 6),
            "risk_reward_ratio": round(self.risk_reward_ratio, 2),
            "trigger_high": round(self.trigger_high, 6),
            "trigger_low": round(self.trigger_low, 6),
            "trigger_range": round(self.trigger_range, 6),
            "atr_value": round(self.atr_value, 6),
        }

    def format_for_message(self) -> str:
        """Format levels for notification message."""
        emoji = "🟢" if self.side == SignalSide.BUY else "🔴"
        return (
            f"{emoji} **{self.side.value} Signal**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"**Entry:** `{self.entry:.6f}`\n"
            f"**Stop Loss:** `{self.stop_loss:.6f}`\n"
            f"**Take Profit:** `{self.take_profit:.6f}`\n"
            f"**R:R Ratio:** `{self.risk_reward_ratio:.2f}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"*Trigger Bar:* High `{self.trigger_high:.6f}` | Low `{self.trigger_low:.6f}`\n"
            f"*Range:* `{self.trigger_range:.6f}` | *ATR(14):* `{self.atr_value:.6f}`"
        )


def calculate_levels(
    candle: pd.Series,
    atr_value: float,
    side: SignalSide,
    entry_retrace: float = 0.236,
    sl_atr_multiplier: float = 0.10,
    tp_extension: float = 0.27,
) -> ExecutionLevels:
    """
    Calculate Fibonacci-based execution levels from trigger candle.

    Long/BUY:
    - Entry: High - (0.236 * Range)  [Pullback limit entry]
    - SL: Low - (0.10 * ATR)         [Buffered against stop hunts]
    - TP: High + (0.27 * Range)      [-0.27 Fib extension]

    Short/SELL:
    - Entry: Low + (0.236 * Range)
    - SL: High + (0.10 * ATR)
    - TP: Low - (0.27 * Range)

    Args:
        candle: Trigger candle (must have high, low, close)
        atr_value: Current ATR(14) value
        side: SignalSide.BUY or SignalSide.SELL
        entry_retrace: Fibonacci retracement for entry (default 0.236)
        sl_atr_multiplier: ATR multiplier for SL buffer (default 0.10)
        tp_extension: Fibonacci extension for TP (default 0.27)

    Returns:
        ExecutionLevels object with all calculated values
    """
    high = candle["high"]
    low = candle["low"]
    candle_range = high - low

    if side == SignalSide.BUY:
        # Long entry: pullback from high
        entry = high - (entry_retrace * candle_range)
        # SL below low with ATR buffer
        stop_loss = low - (sl_atr_multiplier * atr_value)
        # TP at -0.27 extension from high
        take_profit = high + (tp_extension * candle_range)

        risk = entry - stop_loss
        reward = take_profit - entry

    else:  # SELL
        # Short entry: pullback from low
        entry = low + (entry_retrace * candle_range)
        # SL above high with ATR buffer
        stop_loss = high + (sl_atr_multiplier * atr_value)
        # TP at -0.27 extension from low
        take_profit = low - (tp_extension * candle_range)

        risk = stop_loss - entry
        reward = entry - take_profit

    # Risk:Reward ratio
    rr_ratio = reward / risk if risk > 0 else 0

    logger.debug(
        f"Calculated levels for {side.value}: "
        f"Entry={entry:.6f}, SL={stop_loss:.6f}, TP={take_profit:.6f}, "
        f"R:R={rr_ratio:.2f}, Range={candle_range:.6f}, ATR={atr_value:.6f}"
    )

    return ExecutionLevels(
        side=side,
        entry=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_reward_ratio=rr_ratio,
        trigger_high=high,
        trigger_low=low,
        trigger_range=candle_range,
        atr_value=atr_value,
    )


def validate_levels(levels: ExecutionLevels, min_rr: float = 1.0) -> bool:
    """
    Validate execution levels meet minimum criteria.

    Args:
        levels: ExecutionLevels to validate
        min_rr: Minimum acceptable R:R ratio

    Returns:
        True if valid
    """
    if levels.risk_reward_ratio < min_rr:
        logger.warning(
            f"R:R ratio {levels.risk_reward_ratio:.2f} below minimum {min_rr}"
        )
        return False

    if levels.side == SignalSide.BUY:
        if not (levels.stop_loss < levels.entry < levels.take_profit):
            logger.warning("Invalid BUY level order: SL < Entry < TP required")
            return False
    else:
        if not (levels.take_profit < levels.entry < levels.stop_loss):
            logger.warning("Invalid SELL level order: TP < Entry < SL required")
            return False

    return True