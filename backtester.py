"""
Backtester — uses Strategy Registry for auto-discovered strategies.

Usage:
    python backtester.py --strategy BB_RSI_AGGRO --csv ./data/ --csv-tf M1
    python backtester.py --strategy BB_RSI_SCALP --symbol EURUSD --months 6
    python backtester.py --list                     # List all strategies
    python backtester.py --list-symbols             # List broker symbols
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
import pandas as pd
import MetaTrader5 as mt5

from config import (
    MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_PATH,
    ACTIVE_PROP, CURRENT_PHASE,
    FTMO_RULES, FUNDEDNEXT_RULES,
    RISK, STRATEGY,
)
from core.registry import StrategyRegistry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("backtester")


# ════════════════════════════════════════════════════════════
#  MT5 DATA LOADER
# ════════════════════════════════════════════════════════════

TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1, "W1": mt5.TIMEFRAME_W1,
}


def connect_mt5() -> bool:
    if not mt5.initialize(path=MT5_PATH, timeout=60000):
        logger.error(f"MT5 initialize failed: {mt5.last_error()}")
        return False
    if not mt5.login(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        logger.error(f"MT5 login failed: {mt5.last_error()}")
        mt5.shutdown()
        return False
    logger.info(f"MT5 connected — {mt5.account_info().server}")
    return True


def load_candles(symbol: str, timeframe: str, months: int) -> Optional[pd.DataFrame]:
    tf = TIMEFRAME_MAP.get(timeframe)
    if tf is None:
        logger.error(f"Timeframe sconosciuto: {timeframe}")
        return None
    if not mt5.symbol_select(symbol, True):
        logger.error(f"Impossibile selezionare {symbol}")
        return None

    utc_to = datetime.now(timezone.utc)
    utc_from = utc_to - timedelta(days=months * 30)
    rates = mt5.copy_rates_range(symbol, tf, utc_from, utc_to)
    if rates is None or len(rates) == 0:
        logger.error(f"Nessun dato per {symbol} {timeframe}")
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    logger.info(f"  {symbol} {timeframe}: {len(df)} candele ({df.index[0].date()} → {df.index[-1].date()})")
    return df


# ════════════════════════════════════════════════════════════
#  CSV DATA LOADER
# ════════════════════════════════════════════════════════════

def load_csv_candles(filepath: str, symbol: str = None) -> Optional[pd.DataFrame]:
    if not os.path.exists(filepath):
        logger.error(f"File non trovato: {filepath}")
        return None

    try:
        # Peek first line to detect format
        with open(filepath, "r") as f:
            first_line = f.readline().strip()

        first_field = first_line.split(",")[0].strip()
        is_headerless = first_field.replace(".", "").isdigit() and len(first_field) == 8

        if is_headerless:
            # Tickstory headerless: 20210514,00:00:00,O,H,L,C,TV,V,Spread
            n_cols = len(first_line.split(","))
            if n_cols == 9:
                names = ["date_col", "time_col", "open", "high", "low", "close", "tick_volume", "vol2", "spread"]
            elif n_cols == 7:
                names = ["date_col", "time_col", "open", "high", "low", "close", "tick_volume"]
            elif n_cols == 6:
                names = ["date_col", "open", "high", "low", "close", "tick_volume"]
            else:
                names = None
            df = pd.read_csv(filepath, header=None, names=names) if names else pd.read_csv(filepath, header=None)
        else:
            df = pd.read_csv(filepath, sep=None, engine="python")

    except Exception as e:
        logger.error(f"Errore lettura CSV {filepath}: {e}")
        return None

    if df.empty:
        return None

    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    col_map = {
        "gmt_time": "datetime", "timestamp": "datetime",
        "date_time": "datetime", "time": "time_col", "date": "date_col",
        "tickvol": "tick_volume", "tick_vol": "tick_volume",
        "vol": "tick_volume", "volume": "tick_volume",
    }
    df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)

    # Build datetime index
    if "datetime" in df.columns:
        df.index = pd.to_datetime(df["datetime"], utc=True, format="mixed")
    elif "date_col" in df.columns and "time_col" in df.columns:
        date_str = df["date_col"].astype(str)
        time_str = df["time_col"].astype(str)
        sample = date_str.iloc[0]
        if len(sample) == 8 and sample.isdigit():
            date_str = date_str.str[:4] + "-" + date_str.str[4:6] + "-" + date_str.str[6:8]
        df.index = pd.to_datetime(date_str + " " + time_str, utc=True, format="mixed")
    elif "date_col" in df.columns:
        df.index = pd.to_datetime(df["date_col"], utc=True, format="mixed")
    else:
        try:
            df.index = pd.to_datetime(df.iloc[:, 0], utc=True, format="mixed")
        except Exception:
            logger.error(f"Cannot parse datetime: {filepath}")
            return None

    df.index.name = "time"
    for col in ["open", "high", "low", "close"]:
        if col not in df.columns:
            logger.error(f"Colonna '{col}' mancante in {filepath}. Colonne: {list(df.columns)}")
            return None
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if "tick_volume" not in df.columns:
        df["tick_volume"] = 0
    else:
        df["tick_volume"] = pd.to_numeric(df["tick_volume"], errors="coerce")

    df = df[["open", "high", "low", "close", "tick_volume"]].dropna()
    df.sort_index(inplace=True)
    df = df[~df.index.duplicated(keep="first")]

    name = symbol or os.path.basename(filepath)
    logger.info(f"  CSV {name}: {len(df)} candele ({df.index[0].date()} → {df.index[-1].date()})")
    return df


def scan_csv_directory(csv_dir: str) -> dict[str, str]:
    if not os.path.isdir(csv_dir):
        return {}
    symbol_files = {}
    for f in sorted(os.listdir(csv_dir)):
        if not f.lower().endswith(".csv"):
            continue
        name = os.path.splitext(f)[0].upper()
        for suffix in ["_M1", "_M5", "_M15", "_M30", "_H1", "_H4", "_D1", "_TICK", "_2024", "_2025", "_2026"]:
            name = name.replace(suffix, "")
        name = name.replace("-", "").replace("_", "").strip()
        if len(name) >= 6:
            symbol_files[name] = os.path.join(csv_dir, f)
    logger.info(f"  CSV directory: {len(symbol_files)} files in {csv_dir}")
    return symbol_files


def resample_to_timeframe(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    tf_map = {"M1": "1min", "M5": "5min", "M15": "15min", "M30": "30min",
              "H1": "1h", "H4": "4h", "D1": "1D", "W1": "1W"}
    freq = tf_map.get(timeframe)
    if freq is None:
        return df
    return df.resample(freq).agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "tick_volume": "sum",
    }).dropna()


# ════════════════════════════════════════════════════════════
#  TRADE SIMULATOR
# ════════════════════════════════════════════════════════════

class TradeSimulator:
    def __init__(self, initial_balance: float, prop_rules: dict, enforce_prop: bool = True):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.equity = initial_balance
        self.prop_rules = prop_rules
        self.enforce_prop = enforce_prop

        self.trades = []
        self.open_positions = []
        self.equity_curve = []
        self.daily_pnl = {}

        self.peak_balance = initial_balance
        self.max_drawdown = 0.0
        self.max_drawdown_pct = 0.0

        self.day_start_balance = initial_balance
        self.current_day = None
        self.daily_locked = False
        self.prop_violated = False
        self.prop_violation_reason = ""
        self.trading_days = set()

    def run(self, df: pd.DataFrame, symbol: str):
        for i in range(len(df)):
            row = df.iloc[i]
            ts = df.index[i]
            day_str = ts.strftime("%Y-%m-%d")

            if day_str != self.current_day:
                self.current_day = day_str
                self.day_start_balance = self.balance
                self.daily_locked = False

            self._update_positions(row, ts)

            unrealized = sum(self._calc_unrealized(p, row) for p in self.open_positions)
            self.equity = self.balance + unrealized
            self.equity_curve.append({"time": ts, "balance": self.balance, "equity": self.equity})

            if self.equity > self.peak_balance:
                self.peak_balance = self.equity
            dd = self.peak_balance - self.equity
            dd_pct = (dd / self.peak_balance * 100) if self.peak_balance > 0 else 0
            if dd > self.max_drawdown:
                self.max_drawdown = dd
                self.max_drawdown_pct = dd_pct

            if self.enforce_prop and not self.prop_violated:
                violation = self._check_prop_rules()
                if violation:
                    self.prop_violated = True
                    self.prop_violation_reason = violation
                    for pos in list(self.open_positions):
                        self._close_position(pos, row["close"], ts, "PROP_VIOLATION")
                    logger.warning(f"  ⛔ PROP VIOLATION @ {ts}: {violation}")
                    break

            if self.daily_locked or self.prop_violated:
                continue

            signal = row.get("signal")
            if signal and pd.notna(signal):
                self._try_open_trade(row, ts, symbol, signal)

        if len(df) > 0:
            last_row = df.iloc[-1]
            last_ts = df.index[-1]
            for pos in list(self.open_positions):
                self._close_position(pos, last_row["close"], last_ts, "END_OF_DATA")

        return self.trades

    def _try_open_trade(self, row, ts, symbol, direction):
        if len(self.open_positions) >= RISK["max_open_positions"]:
            return
        if any(p["symbol"] == symbol for p in self.open_positions):
            return

        entry = row["close"]
        sl = row["sl"]
        tp = row["tp"]
        if pd.isna(sl) or pd.isna(tp):
            return

        sl_distance = abs(entry - sl)
        if sl_distance <= 0:
            return

        risk_usd = self.balance * RISK["risk_per_trade_pct"] / 100

        self.open_positions.append({
            "symbol": symbol, "direction": direction,
            "entry_price": entry, "sl": sl, "tp": tp,
            "risk_usd": risk_usd, "sl_distance": sl_distance,
            "entry_time": ts, "reason": row.get("reason", ""),
            "be_applied": False,
        })
        self.trading_days.add(ts.strftime("%Y-%m-%d"))

    def _update_positions(self, row, ts):
        to_close = []
        for pos in self.open_positions:
            high, low, close = row["high"], row["low"], row["close"]

            if pos["direction"] == "BUY" and low <= pos["sl"]:
                to_close.append((pos, pos["sl"], "SL_HIT")); continue
            if pos["direction"] == "SELL" and high >= pos["sl"]:
                to_close.append((pos, pos["sl"], "SL_HIT")); continue
            if pos["direction"] == "BUY" and high >= pos["tp"]:
                to_close.append((pos, pos["tp"], "TP_HIT")); continue
            if pos["direction"] == "SELL" and low <= pos["tp"]:
                to_close.append((pos, pos["tp"], "TP_HIT")); continue

            if RISK["breakeven_enabled"] and not pos["be_applied"]:
                trigger = pos["entry_price"] * RISK["breakeven_trigger_pct"] / 100
                if pos["direction"] == "BUY" and close >= pos["entry_price"] + trigger:
                    pos["sl"] = pos["entry_price"] + 0.00002; pos["be_applied"] = True
                elif pos["direction"] == "SELL" and close <= pos["entry_price"] - trigger:
                    pos["sl"] = pos["entry_price"] - 0.00002; pos["be_applied"] = True

            if RISK["trailing_stop_enabled"] and pos["be_applied"]:
                trail = close * RISK["trailing_stop_pct"] / 100
                if pos["direction"] == "BUY" and close > pos["entry_price"]:
                    new_sl = close - trail
                    if new_sl > pos["sl"]: pos["sl"] = new_sl
                elif pos["direction"] == "SELL" and close < pos["entry_price"]:
                    new_sl = close + trail
                    if new_sl < pos["sl"] or pos["sl"] == 0: pos["sl"] = new_sl

        for pos, exit_price, reason in to_close:
            self._close_position(pos, exit_price, ts, reason)

    def _close_position(self, pos, exit_price, ts, exit_reason):
        if pos["direction"] == "BUY":
            price_diff = exit_price - pos["entry_price"]
        else:
            price_diff = pos["entry_price"] - exit_price

        sl_distance = pos["sl_distance"]
        pnl_usd = (price_diff / sl_distance) * pos["risk_usd"] if sl_distance > 0 else 0
        self.balance += pnl_usd

        day_str = ts.strftime("%Y-%m-%d") if hasattr(ts, 'strftime') else str(ts)[:10]
        self.daily_pnl[day_str] = self.daily_pnl.get(day_str, 0) + pnl_usd

        self.trades.append({
            "symbol": pos["symbol"], "direction": pos["direction"],
            "entry_price": pos["entry_price"], "exit_price": exit_price,
            "sl": pos["sl"], "tp": pos["tp"],
            "entry_time": pos["entry_time"], "exit_time": ts,
            "pnl_usd": round(pnl_usd, 2), "risk_usd": round(pos["risk_usd"], 2),
            "exit_reason": exit_reason, "reason": pos["reason"],
            "balance_after": round(self.balance, 2),
        })
        if pos in self.open_positions:
            self.open_positions.remove(pos)

    def _calc_unrealized(self, pos, row):
        diff = (row["close"] - pos["entry_price"]) if pos["direction"] == "BUY" else (pos["entry_price"] - row["close"])
        return (diff / pos["sl_distance"]) * pos["risk_usd"] if pos["sl_distance"] > 0 else 0

    def _check_prop_rules(self):
        daily_loss = self.day_start_balance - self.equity
        max_daily = self.day_start_balance * self.prop_rules["max_daily_loss_pct"] / 100
        if daily_loss >= max_daily:
            return f"Daily drawdown {daily_loss:.2f} >= limit {max_daily:.2f}"
        total_loss = self.initial_balance - self.equity
        max_total = self.initial_balance * self.prop_rules["max_total_loss_pct"] / 100
        if total_loss >= max_total:
            return f"Total drawdown {total_loss:.2f} >= limit {max_total:.2f}"
        buffer = max_daily * RISK["daily_loss_buffer"]
        if daily_loss >= buffer:
            self.daily_locked = True
        return None


# ════════════════════════════════════════════════════════════
#  METRICS
# ════════════════════════════════════════════════════════════

def calculate_metrics(trades, simulator):
    if not trades:
        return {
            "error": "Nessun trade", "total_trades": 0, "wins": 0, "losses": 0,
            "winrate_pct": 0, "total_pnl_usd": 0, "roa_pct": 0,
            "avg_win_usd": 0, "avg_loss_usd": 0, "payoff_ratio": 0,
            "profit_factor": 0, "expectancy_usd": 0,
            "max_drawdown_usd": 0, "max_drawdown_pct": 0, "sharpe_ratio": 0,
            "max_consecutive_wins": 0, "max_consecutive_losses": 0,
            "best_trade_usd": 0, "best_trade_symbol": "N/A",
            "worst_trade_usd": 0, "worst_trade_symbol": "N/A",
            "exit_reasons": {}, "trading_days": 0, "prop_passed": False,
            "prop_violation": "No trades", "min_days_met": False,
            "target_met": False, "duration_days": 0,
            "final_balance": simulator.initial_balance,
        }

    pnls = [t["pnl_usd"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    total_pnl = sum(pnls)
    total_count = len(trades)
    winrate = (len(wins) / total_count * 100) if total_count > 0 else 0
    avg_win = np.mean(wins) if wins else 0
    avg_loss = abs(np.mean(losses)) if losses else 0
    pf = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else float("inf")
    payoff = (avg_win / avg_loss) if avg_loss > 0 else float("inf")
    expectancy = (winrate / 100 * avg_win) - ((1 - winrate / 100) * avg_loss)

    cw = cl = mcw = mcl = 0
    for p in pnls:
        if p > 0: cw += 1; cl = 0; mcw = max(mcw, cw)
        else: cl += 1; cw = 0; mcl = max(mcl, cl)

    sharpe = 0
    if len(pnls) > 1:
        s = pd.Series(pnls)
        sharpe = (s.mean() / s.std()) * np.sqrt(252) if s.std() > 0 else 0

    roa = (total_pnl / simulator.initial_balance * 100)
    best = max(trades, key=lambda t: t["pnl_usd"])
    worst = min(trades, key=lambda t: t["pnl_usd"])
    exit_reasons = {}
    for t in trades:
        exit_reasons[t["exit_reason"]] = exit_reasons.get(t["exit_reason"], 0) + 1

    target_pct = simulator.prop_rules.get("profit_target_pct")
    target_met = total_pnl >= (simulator.initial_balance * target_pct / 100) if target_pct else False

    first_entry = trades[0]["entry_time"]
    last_exit = trades[-1]["exit_time"]
    duration = (last_exit - first_entry).days if hasattr(last_exit - first_entry, 'days') else 0

    return {
        "total_trades": total_count, "wins": len(wins), "losses": len(losses),
        "winrate_pct": round(winrate, 2), "total_pnl_usd": round(total_pnl, 2),
        "roa_pct": round(roa, 2), "avg_win_usd": round(avg_win, 2),
        "avg_loss_usd": round(avg_loss, 2), "payoff_ratio": round(payoff, 2),
        "profit_factor": round(pf, 2), "expectancy_usd": round(expectancy, 2),
        "max_drawdown_usd": round(simulator.max_drawdown, 2),
        "max_drawdown_pct": round(simulator.max_drawdown_pct, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_consecutive_wins": mcw, "max_consecutive_losses": mcl,
        "best_trade_usd": round(best["pnl_usd"], 2),
        "best_trade_symbol": f"{best['symbol']} {best['direction']}",
        "worst_trade_usd": round(worst["pnl_usd"], 2),
        "worst_trade_symbol": f"{worst['symbol']} {worst['direction']}",
        "exit_reasons": exit_reasons,
        "trading_days": len(simulator.trading_days),
        "prop_passed": not simulator.prop_violated,
        "prop_violation": simulator.prop_violation_reason,
        "min_days_met": len(simulator.trading_days) >= simulator.prop_rules.get("min_trading_days", 0),
        "target_met": target_met, "duration_days": duration,
        "final_balance": round(simulator.balance, 2),
    }


# ════════════════════════════════════════════════════════════
#  REPORT PRINTERS
# ════════════════════════════════════════════════════════════

def print_report(metrics, strategy_name, symbols, prop, phase):
    sep = "═" * 62
    print(f"\n{sep}")
    print(f"  📊 BACKTEST REPORT — {strategy_name}")
    print(f"{sep}")
    print(f"  Prop: {prop} {phase}")
    print(f"  Symbols: {', '.join(symbols[:10])}{' ...' if len(symbols) > 10 else ''}")
    print(f"  Duration: {metrics['duration_days']} days")
    print(f"{sep}\n")

    pnl_icon = "🟢" if metrics["total_pnl_usd"] >= 0 else "🔴"
    dd_icon = "🟢" if metrics["max_drawdown_pct"] < 5 else ("🟡" if metrics["max_drawdown_pct"] < 8 else "🔴")

    print(f"  {pnl_icon} P&L: ${metrics['total_pnl_usd']:+,.2f} ({metrics['roa_pct']:+.2f}%)  |  Balance: ${metrics['final_balance']:,.2f}")
    print(f"     PF: {metrics['profit_factor']:.2f}  |  Sharpe: {metrics['sharpe_ratio']:.2f}  |  Expectancy: ${metrics['expectancy_usd']:+.2f}/trade")
    print(f"     Trades: {metrics['total_trades']}  |  Win: {metrics['wins']}  Loss: {metrics['losses']}  |  WR: {metrics['winrate_pct']:.1f}%")
    print(f"     Avg Win: ${metrics['avg_win_usd']:+,.2f}  |  Avg Loss: ${-metrics['avg_loss_usd']:+,.2f}  |  Payoff: {metrics['payoff_ratio']:.2f}")
    print(f"  {dd_icon} Max DD: ${metrics['max_drawdown_usd']:,.2f} ({metrics['max_drawdown_pct']:.2f}%)")
    print(f"     Streaks: {metrics['max_consecutive_wins']}W / {metrics['max_consecutive_losses']}L")

    for reason, count in metrics["exit_reasons"].items():
        pct = count / metrics["total_trades"] * 100 if metrics["total_trades"] else 0
        icon = {"TP_HIT": "🎯", "SL_HIT": "🛑", "END_OF_DATA": "⏹️", "PROP_VIOLATION": "⛔"}.get(reason, "•")
        print(f"     {icon} {reason}: {count} ({pct:.1f}%)")

    dd_ok = "✅" if metrics["prop_passed"] else "❌"
    days_ok = "✅" if metrics["min_days_met"] else "❌"
    target_ok = "✅" if metrics["target_met"] else "❌"
    print(f"\n  PROP: {dd_ok} DD  {days_ok} Days({metrics['trading_days']})  {target_ok} Target")
    if metrics["prop_violation"]:
        print(f"  ⛔ {metrics['prop_violation']}")

    passed_all = metrics["prop_passed"] and metrics["min_days_met"] and metrics["target_met"]
    print(f"\n  {'🏆 CHALLENGE SUPERATA!' if passed_all else '❌ CHALLENGE NON SUPERATA'}")
    print()


def print_per_symbol_report(trades):
    if not trades:
        return
    by_symbol = {}
    for t in trades:
        by_symbol.setdefault(t["symbol"], []).append(t)

    print(f"\n{'═' * 90}")
    print(f"  📊 PERFORMANCE PER SIMBOLO")
    print(f"{'═' * 90}")
    print(f"  {'Simbolo':<14} {'Trade':>6} {'Win':>5} {'Loss':>5} {'WR%':>7} {'P&L $':>12} {'PF':>6}")
    print(f"  {'─' * 58}")

    stats = []
    for sym, sym_trades in by_symbol.items():
        pnls = [t["pnl_usd"] for t in sym_trades]
        w = [p for p in pnls if p > 0]
        l = [p for p in pnls if p <= 0]
        pf = (sum(w) / abs(sum(l))) if l and sum(l) != 0 else float("inf")
        wr = (len(w) / len(pnls) * 100) if pnls else 0
        stats.append({"symbol": sym, "trades": len(pnls), "wins": len(w), "losses": len(l),
                       "wr": wr, "pnl": sum(pnls), "pf": pf})

    for s in sorted(stats, key=lambda x: x["pnl"], reverse=True):
        e = "🟢" if s["pnl"] >= 0 else "🔴"
        pf_s = f"{s['pf']:.2f}" if s['pf'] < 100 else "∞"
        print(f"  {e} {s['symbol']:<12} {s['trades']:>6} {s['wins']:>5} {s['losses']:>5} {s['wr']:>6.1f}% {s['pnl']:>+11,.2f} {pf_s:>6}")

    prof = sum(1 for s in stats if s["pnl"] > 0)
    print(f"  {'─' * 58}")
    print(f"  Profittevoli: {prof}/{len(stats)}")
    print(f"{'═' * 90}\n")


# ════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Prop Bot — Backtester")
    parser.add_argument("--strategy", type=str, default=None, help="Strategy name")
    parser.add_argument("--symbol", type=str, default=None, help="Single symbol")
    parser.add_argument("--months", type=int, default=6, help="MT5 months lookback")
    parser.add_argument("--csv", type=str, default=None, help="CSV file or directory")
    parser.add_argument("--csv-tf", type=str, default="M1", help="CSV timeframe")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--no-prop", action="store_true")
    parser.add_argument("--list", action="store_true", help="List all strategies")
    parser.add_argument("--list-symbols", action="store_true")
    args = parser.parse_args()

    # ── Discover strategies ──
    StrategyRegistry.discover()

    if args.list:
        StrategyRegistry.print_catalog()
        return

    if not args.strategy:
        logger.error("Specifica --strategy. Usa --list per vedere le disponibili.")
        return

    # ── Load strategy ──
    strategy_name = args.strategy.upper()
    strategy = StrategyRegistry.get(strategy_name)
    if not strategy:
        return

    strat_tf = strategy.timeframe()
    strat_symbols = [args.symbol.upper()] if args.symbol else strategy.symbols()
    htf_tf = strategy.htf_timeframe() or "H4"

    # ── Prop rules ──
    rules_map = {"FTMO": FTMO_RULES, "FUNDEDNEXT": FUNDEDNEXT_RULES}
    prop_rules = rules_map[ACTIVE_PROP][CURRENT_PHASE]
    initial_balance = prop_rules["account_size"]

    # ── Load data ──
    print()
    data_cache = {}
    htf_cache = {}

    if args.csv:
        logger.info(f"📁 CSV mode — {strategy_name} on {strat_tf}")
        csv_tf = args.csv_tf

        if os.path.isdir(args.csv):
            symbol_files = scan_csv_directory(args.csv)
            for sym, filepath in symbol_files.items():
                if args.symbol and sym != args.symbol.upper():
                    continue
                if sym not in [s.upper() for s in strat_symbols] and not args.symbol:
                    continue
                df = load_csv_candles(filepath, sym)
                if df is not None:
                    if csv_tf != strat_tf:
                        df = resample_to_timeframe(df, strat_tf)
                    data_cache[sym] = df
                    htf = resample_to_timeframe(df if csv_tf == strat_tf else df, htf_tf)
                    if len(htf) > 0:
                        htf_cache[sym] = htf
        elif os.path.isfile(args.csv):
            sym = args.symbol.upper() if args.symbol else os.path.splitext(os.path.basename(args.csv))[0].upper().split("_")[0]
            df = load_csv_candles(args.csv, sym)
            if df is not None:
                if csv_tf != strat_tf:
                    df = resample_to_timeframe(df, strat_tf)
                data_cache[sym] = df
                htf = resample_to_timeframe(df, htf_tf)
                if len(htf) > 0:
                    htf_cache[sym] = htf
    else:
        logger.info(f"MT5 mode — {strategy_name} on {strat_tf}")
        if args.list_symbols:
            if connect_mt5():
                from mt5_handler import MT5Handler
                h = MT5Handler(); h._connected = True; h.print_symbol_catalog()
                mt5.shutdown()
            return

        if not connect_mt5():
            sys.exit(1)
        for sym in strat_symbols:
            df = load_candles(sym, strat_tf, args.months)
            if df is not None:
                data_cache[sym] = df
            htf = load_candles(sym, htf_tf, args.months)
            if htf is not None:
                htf_cache[sym] = htf
        mt5.shutdown()

    if not data_cache:
        logger.error("Nessun dato caricato")
        sys.exit(1)

    logger.info(f"Data: {len(data_cache)} symbols loaded")

    # ── Run backtest ──
    logger.info(f"\n{'='*50}\nBACKTEST: {strategy_name}\n{'='*50}")

    simulator = TradeSimulator(
        initial_balance=initial_balance,
        prop_rules=prop_rules,
        enforce_prop=not args.no_prop,
    )

    for sym, df in data_cache.items():
        logger.info(f"  Segnali {strategy_name} su {sym} ({strat_tf})...")
        htf = htf_cache.get(sym)
        df_signals = strategy.generate_signals_batch(df, htf)
        sig_count = df_signals["signal"].notna().sum()
        buys = (df_signals["signal"] == "BUY").sum()
        sells = (df_signals["signal"] == "SELL").sum()
        logger.info(f"  Segnali generati: {sig_count} (BUY: {buys}, SELL: {sells})")
        simulator.run(df_signals, sym)

    metrics = calculate_metrics(simulator.trades, simulator)
    tested_symbols = list(data_cache.keys())
    print_report(metrics, strategy_name, tested_symbols, ACTIVE_PROP, CURRENT_PHASE)

    if simulator.trades:
        print_per_symbol_report(simulator.trades)

    if args.export and simulator.trades:
        os.makedirs("backtest_results", exist_ok=True)
        pd.DataFrame(simulator.trades).to_csv(f"backtest_results/{strategy_name}_trades.csv", index=False)
        pd.DataFrame(simulator.equity_curve).to_csv(f"backtest_results/{strategy_name}_equity.csv", index=False)
        logger.info(f"📁 Exported to backtest_results/")

    logger.info("Backtest completato ✅")


if __name__ == "__main__":
    main()
