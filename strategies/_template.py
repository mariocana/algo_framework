"""
Strategy Template — Copy this file to create a new strategy.

Steps:
  1. Copy this file: cp _template.py my_strategy.py
  2. Rename the class
  3. Set name, default_config, symbols, timeframe
  4. Implement generate_signal() and generate_signals_batch()
  5. Done! The framework auto-discovers it.

Run your strategy:
  python pipeline.py --strategy MY_STRATEGY --csv ./data/ --csv-tf M1
"""

from typing import Optional
import pandas as pd
import numpy as np

from core.base_strategy import BaseStrategy, Signal
from core import indicators as ind


class MyStrategy(BaseStrategy):
    """
    Describe your strategy here.
    What market conditions does it exploit? What's the edge?
    """

    @property
    def name(self) -> str:
        # Unique identifier — used in CLI: --strategy MY_STRATEGY
        return "MY_STRATEGY"

    @property
    def default_config(self) -> dict:
        # All tunable parameters go here.
        # Users can override these in config.py
        return {
            "fast_period": 9,
            "slow_period": 21,
            "entry_timeframe": "M15",
            "htf_timeframe": "H4",
            "symbols": ["EURUSD", "GBPUSD"],
        }

    def symbols(self) -> list[str]:
        return self.cfg["symbols"]

    def timeframe(self) -> str:
        return self.cfg["entry_timeframe"]

    def generate_signal(self, symbol: str) -> Optional[Signal]:
        """
        LIVE MODE: called every scan cycle for each symbol.
        Fetch candles from MT5, compute indicators, return Signal or None.
        """
        df = self.mt5.get_candles(symbol, self.timeframe(), 300)
        if df is None or len(df) < 50:
            return None

        # ── Compute your indicators ──
        # df["fast_ema"] = ind.ema(df["close"], self.cfg["fast_period"])
        # df["slow_ema"] = ind.ema(df["close"], self.cfg["slow_period"])

        # ── Check conditions ──
        # curr = df.iloc[-1]
        # prev = df.iloc[-2]
        # if curr["fast_ema"] > curr["slow_ema"] and prev["fast_ema"] <= prev["slow_ema"]:
        #     return Signal(
        #         symbol=symbol, direction="BUY",
        #         entry=curr["close"], sl=..., tp=...,
        #         strategy=self.name, reason="My buy reason"
        #     )

        return None

    def generate_signals_batch(self, df: pd.DataFrame, htf_df=None) -> pd.DataFrame:
        """
        BACKTEST MODE: process entire DataFrame, add signal columns.
        Must set: df["signal"], df["sl"], df["tp"], df["reason"]
        """
        df = df.copy()
        df["signal"] = None
        df["sl"] = np.nan
        df["tp"] = np.nan
        df["reason"] = ""

        # ── Compute indicators on full series ──
        # df["fast_ema"] = ind.ema(df["close"], self.cfg["fast_period"])
        # df["slow_ema"] = ind.ema(df["close"], self.cfg["slow_period"])
        # df["atr"] = ind.atr(df, 14)

        # ── Loop through bars ──
        # for i in range(1, len(df)):
        #     curr = df.iloc[i]
        #     prev = df.iloc[i - 1]
        #     price = curr["close"]
        #
        #     # BUY condition
        #     if your_buy_condition:
        #         df.iloc[i, df.columns.get_loc("signal")] = "BUY"
        #         df.iloc[i, df.columns.get_loc("sl")] = price - curr["atr"] * 1.5
        #         df.iloc[i, df.columns.get_loc("tp")] = price + curr["atr"] * 3.0
        #         df.iloc[i, df.columns.get_loc("reason")] = "My reason"
        #
        #     # SELL condition
        #     elif your_sell_condition:
        #         ...

        return df
