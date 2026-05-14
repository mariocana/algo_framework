"""
BB + RSI Scalp — Conservative mean reversion for funded management.
BB(40) + RSI(5) + ADX < 25 filter.
"""

from typing import Optional
import pandas as pd
import numpy as np

from core.base_strategy import BaseStrategy, Signal
from core import indicators as ind


class BBRSIScalp(BaseStrategy):

    @property
    def name(self) -> str:
        return "BB_RSI_SCALP"

    @property
    def default_config(self) -> dict:
        return {
            "bb_period": 40,
            "bb_std_dev": 2.0,
            "rsi_period": 5,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "adx_period": 14,
            "adx_max": 25,
            "swing_lookback": 10,
            "sl_buffer_pips": 3,
            "min_rr": 0.8,
            "entry_timeframe": "M5",
            "htf_timeframe": "H4",
            "symbols": [
                "GBPUSD", "EURUSD", "AUDCAD",
                "GBPCHF", "AUDNZD", "USDCHF",
            ],
        }

    def symbols(self) -> list[str]:
        return self.cfg["symbols"]

    def timeframe(self) -> str:
        return self.cfg["entry_timeframe"]

    def generate_signal(self, symbol: str) -> Optional[Signal]:
        """Live signal generation."""
        df = self.mt5.get_candles(symbol, self.timeframe(), 500)
        if df is None or len(df) < self.cfg["bb_period"] + 50:
            return None
        return self._check_signal(df, symbol)

    def generate_signals_batch(self, df: pd.DataFrame, htf_df=None) -> pd.DataFrame:
        """Backtest signal generation across full DataFrame."""
        df = df.copy()
        df["signal"] = None
        df["sl"] = np.nan
        df["tp"] = np.nan
        df["reason"] = ""

        c = self.cfg
        df["bb_upper"], df["bb_mid"], df["bb_lower"] = ind.bollinger_bands(
            df["close"], c["bb_period"], c["bb_std_dev"]
        )
        df["rsi"] = ind.rsi(df["close"], c["rsi_period"])
        df["adx"] = ind.adx(df, c["adx_period"])

        for i in range(1, len(df)):
            curr = df.iloc[i]
            prev = df.iloc[i - 1]

            if pd.isna(curr["adx"]) or curr["adx"] > c["adx_max"]:
                continue
            if pd.isna(curr["rsi"]) or pd.isna(curr["bb_lower"]):
                continue

            price = curr["close"]
            signal, sl, tp, reason = self._evaluate_bar(df, i, curr, prev, price)

            if signal:
                df.iloc[i, df.columns.get_loc("signal")] = signal
                df.iloc[i, df.columns.get_loc("sl")] = sl
                df.iloc[i, df.columns.get_loc("tp")] = tp
                df.iloc[i, df.columns.get_loc("reason")] = reason

        return df

    def _evaluate_bar(self, df, i, curr, prev, price):
        """Core logic shared between live and backtest."""
        c = self.cfg

        # Estimate point for SL buffer
        point = 0.01 if price > 100 else (0.001 if price > 10 else 0.0001)
        sl_buf = c["sl_buffer_pips"] * point * 10
        swing_lb = c["swing_lookback"]

        # LONG: price touches lower BB + RSI exits oversold
        if (curr["low"] <= curr["bb_lower"]
                and prev["rsi"] < c["rsi_oversold"]
                and curr["rsi"] >= c["rsi_oversold"]):

            start = max(0, i - swing_lb)
            swing_low = df["low"].iloc[start:i + 1].min()
            sl = round(swing_low - sl_buf, 5)
            tp = round(curr["bb_upper"], 5)

            risk = abs(price - sl)
            reward = abs(tp - price)
            if risk > 0 and (reward / risk) >= c["min_rr"]:
                reason = (
                    f"BB({c['bb_period']}) lower + RSI({c['rsi_period']}) "
                    f"exit oversold. ADX={curr['adx']:.1f}"
                )
                return "BUY", sl, tp, reason

        # SHORT: price touches upper BB + RSI exits overbought
        if (curr["high"] >= curr["bb_upper"]
                and prev["rsi"] > c["rsi_overbought"]
                and curr["rsi"] <= c["rsi_overbought"]):

            start = max(0, i - swing_lb)
            swing_high = df["high"].iloc[start:i + 1].max()
            sl = round(swing_high + sl_buf, 5)
            tp = round(curr["bb_lower"], 5)

            risk = abs(sl - price)
            reward = abs(price - tp)
            if risk > 0 and (reward / risk) >= c["min_rr"]:
                reason = (
                    f"BB({c['bb_period']}) upper + RSI({c['rsi_period']}) "
                    f"exit overbought. ADX={curr['adx']:.1f}"
                )
                return "SELL", sl, tp, reason

        return None, None, None, None

    def _check_signal(self, df, symbol):
        """Check signal on latest bars (live mode)."""
        c = self.cfg
        bb_u, bb_m, bb_l = ind.bollinger_bands(df["close"], c["bb_period"], c["bb_std_dev"])
        df["bb_upper"] = bb_u
        df["bb_lower"] = bb_l
        df["rsi"] = ind.rsi(df["close"], c["rsi_period"])
        df["adx"] = ind.adx(df, c["adx_period"])

        i = len(df) - 1
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        price = curr["close"]

        if pd.isna(curr["adx"]) or curr["adx"] > c["adx_max"]:
            return None

        signal, sl, tp, reason = self._evaluate_bar(df, i, curr, prev, price)
        if signal:
            return Signal(
                symbol=symbol, direction=signal, entry=price,
                sl=sl, tp=tp, strategy=self.name, reason=reason,
            )
        return None
