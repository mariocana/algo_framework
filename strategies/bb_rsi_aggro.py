"""
BB + RSI Aggro — Aggressive mean reversion for challenge pass.
BB(20) + RSI(3) + ADX < 30 filter. Higher frequency, tighter SL.
"""

from typing import Optional
import pandas as pd
import numpy as np

from core.base_strategy import BaseStrategy, Signal
from core import indicators as ind


class BBRSIAggro(BaseStrategy):

    @property
    def name(self) -> str:
        return "BB_RSI_AGGRO"

    @property
    def default_config(self) -> dict:
        return {
            "bb_period": 20,
            "bb_std_dev": 2.0,
            "rsi_period": 3,
            "rsi_oversold": 25,
            "rsi_overbought": 75,
            "adx_period": 14,
            "adx_max": 30,
            "swing_lookback": 5,
            "sl_buffer_pips": 2,
            "min_rr": 0.7,
            "entry_timeframe": "M5",
            "htf_timeframe": "H4",
            "symbols": [
                "GBPCHF", "AUDCAD", "AUDNZD", "EURUSD",
                "CADCHF", "EURCHF", "USDCAD", "NZDUSD",
            ],
        }

    def symbols(self) -> list[str]:
        return self.cfg["symbols"]

    def timeframe(self) -> str:
        return self.cfg["entry_timeframe"]

    def generate_signal(self, symbol: str) -> Optional[Signal]:
        df = self.mt5.get_candles(symbol, self.timeframe(), 500)
        if df is None or len(df) < self.cfg["bb_period"] + 50:
            return None
        return self._check_signal(df, symbol)

    def generate_signals_batch(self, df: pd.DataFrame, htf_df=None) -> pd.DataFrame:
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
        c = self.cfg
        point = 0.01 if price > 100 else (0.001 if price > 10 else 0.0001)
        sl_buf = c["sl_buffer_pips"] * point * 10
        swing_lb = c["swing_lookback"]

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
                return "BUY", sl, tp, f"⚡ AGGRO BB lower + RSI exit oversold. ADX={curr['adx']:.1f}"

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
                return "SELL", sl, tp, f"⚡ AGGRO BB upper + RSI exit overbought. ADX={curr['adx']:.1f}"

        return None, None, None, None

    def _check_signal(self, df, symbol):
        c = self.cfg
        df["bb_upper"], _, df["bb_lower"] = ind.bollinger_bands(df["close"], c["bb_period"], c["bb_std_dev"])
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
            return Signal(symbol=symbol, direction=signal, entry=price,
                          sl=sl, tp=tp, strategy=self.name, reason=reason)
        return None
