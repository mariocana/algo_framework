"""
Base Strategy — Abstract class that every strategy must implement.

To create a new strategy:
  1. Create a file in strategies/ (e.g. strategies/my_strategy.py)
  2. Subclass BaseStrategy
  3. Implement the required methods
  4. Register it in strategies/__init__.py

The framework handles everything else: backtest, robustness, live execution.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════
#  SIGNAL — standardized output from every strategy
# ════════════════════════════════════════════════════════════

@dataclass
class Signal:
    """Standardized trade signal produced by any strategy."""
    symbol: str
    direction: str          # "BUY" or "SELL"
    entry: float
    sl: float
    tp: float
    strategy: str           # Strategy name
    reason: str             # Human-readable reason
    strength: float = 1.0   # 0-1 confidence

    def __post_init__(self):
        risk = abs(self.entry - self.sl)
        reward = abs(self.tp - self.entry)
        self.rr_ratio = round(reward / risk, 2) if risk > 0 else 0
        self.sl_distance_points = abs(self.entry - self.sl)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "entry": self.entry,
            "sl": self.sl,
            "tp": self.tp,
            "strategy": self.strategy,
            "reason": self.reason,
            "strength": self.strength,
            "rr_ratio": self.rr_ratio,
        }

    def __repr__(self):
        return (
            f"Signal({self.symbol} {self.direction} @ {self.entry:.5f} | "
            f"SL={self.sl:.5f} TP={self.tp:.5f} | RR={self.rr_ratio} | "
            f"{self.strategy})"
        )


# ════════════════════════════════════════════════════════════
#  BASE STRATEGY — implement this to add new strategies
# ════════════════════════════════════════════════════════════

class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.

    Subclasses MUST implement:
      - name:             strategy identifier
      - default_config:   default parameters
      - symbols():        which symbols to trade
      - timeframe():      entry timeframe
      - generate_signal(): live signal generation (one bar at a time)
      - generate_signals_batch(): backtest signal generation (whole DataFrame)

    The framework calls these methods — you never call them directly.
    """

    def __init__(self, config: dict = None, mt5_handler=None):
        """
        Args:
            config: strategy-specific config dict (merged with default_config)
            mt5_handler: MT5Handler instance for live trading (None in backtest)
        """
        self.mt5 = mt5_handler
        self.cfg = {**self.default_config}
        if config:
            self.cfg.update(config)

    # ── Required Properties ──────────────────────────────

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique strategy identifier. e.g. 'BB_RSI_SCALP'"""
        pass

    @property
    @abstractmethod
    def default_config(self) -> dict:
        """
        Default strategy parameters.
        These can be overridden via config.py or CLI.

        Example:
            return {
                "bb_period": 20,
                "rsi_period": 5,
                "rsi_oversold": 30,
                "rsi_overbought": 70,
                "entry_timeframe": "M5",
                "symbols": ["EURUSD", "GBPUSD"],
            }
        """
        pass

    # ── Required Methods ─────────────────────────────────

    @abstractmethod
    def symbols(self) -> list[str]:
        """
        Return list of symbols this strategy trades.
        Can be a static list or dynamic (from broker).
        """
        pass

    @abstractmethod
    def timeframe(self) -> str:
        """Return the entry timeframe. e.g. 'M5', 'M1', 'H1'"""
        pass

    @abstractmethod
    def generate_signal(self, symbol: str) -> Optional[Signal]:
        """
        Generate a signal for ONE symbol at the CURRENT bar.
        Used in LIVE trading — called every scan cycle.

        Must fetch candles internally (via self.mt5.get_candles).
        Returns Signal if entry conditions are met, None otherwise.
        """
        pass

    @abstractmethod
    def generate_signals_batch(
        self, df: pd.DataFrame, htf_df: Optional[pd.DataFrame] = None
    ) -> pd.DataFrame:
        """
        Generate signals across an ENTIRE DataFrame.
        Used in BACKTESTING — processes all bars at once.

        Must add columns to df: 'signal', 'sl', 'tp', 'reason'
        - signal: "BUY", "SELL", or None
        - sl: stop loss price
        - tp: take profit price
        - reason: human-readable reason string

        Args:
            df: OHLCV DataFrame (indexed by time)
            htf_df: Optional higher-timeframe DataFrame for trend filter

        Returns:
            df with signal columns added
        """
        pass

    # ── Optional Methods (override if needed) ────────────

    def htf_timeframe(self) -> Optional[str]:
        """Higher timeframe for trend filter. None = no HTF filter."""
        return self.cfg.get("htf_timeframe", "H4")

    def min_bars_required(self) -> int:
        """Minimum number of bars needed to compute indicators."""
        return self.cfg.get("min_bars", 200)

    def on_trade_opened(self, trade: dict):
        """Called when a trade is opened. Override for custom logic."""
        pass

    def on_trade_closed(self, trade: dict):
        """Called when a trade is closed. Override for custom logic."""
        pass

    # ── Helper Methods (available to all strategies) ─────

    def scan_all(self) -> list[Signal]:
        """Scan all symbols for signals (live mode)."""
        signals = []
        for symbol in self.symbols():
            signal = self.generate_signal(symbol)
            if signal:
                signals.append(signal)
        return signals
