"""
State management for tracking processed candles and active trades.
Persists to JSON file for restart resilience.
"""
import json
import logging
import threading
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any

from src.core.config import get_settings

logger = logging.getLogger(__name__)


def _make_key(symbol: str, timeframe: str) -> str:
    """Create a composite key for symbol + timeframe."""
    return f"{symbol}:{timeframe}"


def _parse_key(key: str) -> tuple[str, str]:
    """Parse composite key back to symbol and timeframe."""
    parts = key.split(":", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    # Legacy format: no timeframe, assume primary timeframe
    return key, "1h"


@dataclass
class CandleState:
    """State for a single symbol's last processed candle."""
    symbol: str
    timeframe: str
    last_candle_timestamp: int  # milliseconds
    last_candle_close: float
    updated_at: str  # ISO format

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CandleState":
        # Handle legacy data without timeframe
        if "timeframe" not in data:
            data["timeframe"] = "1h"
        return cls(**data)


@dataclass
class ActiveTrade:
    """Active trade tracking for consecutive signal prevention."""
    symbol: str
    timeframe: str
    side: str  # "BUY" or "SELL"
    entry_price: float
    stop_loss: float
    take_profit: float
    trigger_candle_timestamp: int
    trigger_high: float
    trigger_low: float
    created_at: str  # ISO format

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActiveTrade":
        # Handle legacy data without timeframe
        if "timeframe" not in data:
            data["timeframe"] = "1h"
        return cls(**data)

    def check_exit(self, current_price: float) -> Optional[str]:
        """Check if trade hit TP or SL. Returns 'TP', 'SL', or None."""
        if self.side == "BUY":
            if current_price >= self.take_profit:
                return "TP"
            if current_price <= self.stop_loss:
                return "SL"
        else:  # SELL
            if current_price <= self.take_profit:
                return "TP"
            if current_price >= self.stop_loss:
                return "SL"
        return None


class StateManager:
    """Thread-safe state manager with JSON persistence."""

    def __init__(
        self,
        persist_file: Optional[str] = None,
        persist_enabled: bool = True,
        settings: Optional["Settings"] = None
    ):
        from src.core.config import get_settings
        self.settings = settings or get_settings()
        self.persist_enabled = persist_enabled
        self.persist_file = Path(persist_file or self.settings.state.persist_file)
        self._lock = threading.RLock()
        self._candle_states: Dict[str, CandleState] = {}  # key: "symbol:timeframe"
        self._active_trades: Dict[str, ActiveTrade] = {}  # key: "symbol:timeframe"

        # Ensure parent directory exists
        self.persist_file.parent.mkdir(parents=True, exist_ok=True)

        # Load persisted state
        self._load()

    def _load(self) -> None:
        """Load state from JSON file."""
        if not self.persist_enabled or not self.persist_file.exists():
            logger.debug("No persisted state file found or persistence disabled")
            return

        try:
            with open(self.persist_file, "r") as f:
                data = json.load(f)

            # Load candle states
            for key, state_data in data.get("candle_states", {}).items():
                self._candle_states[key] = CandleState.from_dict(state_data)

            # Load active trades
            for key, trade_data in data.get("active_trades", {}).items():
                self._active_trades[key] = ActiveTrade.from_dict(trade_data)

            logger.info(
                f"Loaded state: {len(self._candle_states)} candle states, "
                f"{len(self._active_trades)} active trades"
            )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to load state file, starting fresh: {e}")
            self._candle_states.clear()
            self._active_trades.clear()

    def _save(self) -> None:
        """Save state to JSON file."""
        if not self.persist_enabled:
            return

        try:
            data = {
                "candle_states": {
                    key: state.to_dict()
                    for key, state in self._candle_states.items()
                },
                "active_trades": {
                    key: trade.to_dict()
                    for key, trade in self._active_trades.items()
                },
                "saved_at": datetime.utcnow().isoformat(),
            }

            # Atomic write via temp file
            temp_file = self.persist_file.with_suffix(".tmp")
            with open(temp_file, "w") as f:
                json.dump(data, f, indent=2)
            temp_file.replace(self.persist_file)

            logger.debug("State saved successfully")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    # ============================================
    # Candle State Methods
    # ============================================

    def get_last_candle_timestamp(self, symbol: str, timeframe: str) -> Optional[int]:
        """Get the timestamp of the last processed candle for a symbol/timeframe."""
        with self._lock:
            key = _make_key(symbol, timeframe)
            state = self._candle_states.get(key)
            return state.last_candle_timestamp if state else None

    def update_candle_state(
        self,
        symbol: str,
        timeframe: str,
        timestamp: int,
        close_price: float
    ) -> None:
        """Update the last processed candle for a symbol/timeframe."""
        with self._lock:
            key = _make_key(symbol, timeframe)
            self._candle_states[key] = CandleState(
                symbol=symbol,
                timeframe=timeframe,
                last_candle_timestamp=timestamp,
                last_candle_close=close_price,
                updated_at=datetime.utcnow().isoformat(),
            )
            self._save()

    def is_new_candle(self, symbol: str, timeframe: str, timestamp: int) -> bool:
        """Check if the given timestamp represents a new candle for symbol/timeframe."""
        with self._lock:
            last_ts = self.get_last_candle_timestamp(symbol, timeframe)
            if last_ts is None:
                return True
            return timestamp > last_ts

    # ============================================
    # Active Trade Methods
    # ============================================

    def get_active_trade(self, symbol: str, timeframe: str) -> Optional[ActiveTrade]:
        """Get active trade for a symbol/timeframe."""
        with self._lock:
            key = _make_key(symbol, timeframe)
            return self._active_trades.get(key)

    def has_active_trade(self, symbol: str, timeframe: str) -> bool:
        """Check if there's an active trade for a symbol/timeframe."""
        with self._lock:
            key = _make_key(symbol, timeframe)
            return key in self._active_trades

    def set_active_trade(
        self,
        symbol: str,
        timeframe: str,
        side: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        trigger_candle_timestamp: int,
        trigger_high: float,
        trigger_low: float
    ) -> None:
        """Record a new active trade."""
        with self._lock:
            key = _make_key(symbol, timeframe)
            self._active_trades[key] = ActiveTrade(
                symbol=symbol,
                timeframe=timeframe,
                side=side,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                trigger_candle_timestamp=trigger_candle_timestamp,
                trigger_high=trigger_high,
                trigger_low=trigger_low,
                created_at=datetime.utcnow().isoformat(),
            )
            self._save()
            logger.info(f"Active trade set for {symbol} [{timeframe}]: {side} @ {entry_price}")

    def check_and_clear_active_trade(self, symbol: str, timeframe: str, current_price: float) -> Optional[str]:
        """Check if active trade hit TP/SL, clear if so. Returns exit reason or None."""
        with self._lock:
            key = _make_key(symbol, timeframe)
            trade = self._active_trades.get(key)
            if not trade:
                return None

            exit_reason = trade.check_exit(current_price)
            if exit_reason:
                logger.info(
                    f"Active trade for {symbol} [{timeframe}] hit {exit_reason}: "
                    f"{trade.side} entry={trade.entry_price}, "
                    f"SL={trade.stop_loss}, TP={trade.take_profit}, "
                    f"current={current_price}"
                )
                del self._active_trades[key]
                self._save()
                return exit_reason

            return None

    def clear_active_trade(self, symbol: str, timeframe: str) -> bool:
        """Manually clear active trade (e.g., on manual exit)."""
        with self._lock:
            key = _make_key(symbol, timeframe)
            if key in self._active_trades:
                del self._active_trades[key]
                self._save()
                logger.info(f"Active trade cleared for {symbol} [{timeframe}]")
                return True
            return False

    def get_all_active_trades(self) -> Dict[str, ActiveTrade]:
        """Get all active trades (copy)."""
        with self._lock:
            return dict(self._active_trades)

    def get_all_candle_states(self) -> Dict[str, CandleState]:
        """Get all candle states (copy)."""
        with self._lock:
            return dict(self._candle_states)