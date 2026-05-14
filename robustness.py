"""
Robustness Tester — Walk-Forward + Monte Carlo using Strategy Registry.

Usage:
    python robustness.py --strategy BB_RSI_AGGRO --csv ./data/ --csv-tf M1
"""

import argparse
import logging
import os
import sys
from typing import Optional

import numpy as np
import pandas as pd

from config import (
    ACTIVE_PROP, CURRENT_PHASE,
    FTMO_RULES, FUNDEDNEXT_RULES,
    RISK, STRATEGY,
)
from core.registry import StrategyRegistry
from backtester import (
    load_csv_candles, scan_csv_directory, resample_to_timeframe,
    load_candles, connect_mt5,
    TradeSimulator, calculate_metrics,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("robustness")


class WalkForwardAnalysis:
    def __init__(self, train_months=6, test_months=2, step_months=2):
        self.train_months = train_months
        self.test_months = test_months
        self.step_months = step_months

    def run(self, data, htf_data, strategy, prop_rules, initial_balance):
        first_sym = next(iter(data))
        data_start = data[first_sym].index[0]
        data_end = data[first_sym].index[-1]
        total_days = (data_end - data_start).days

        train_days = self.train_months * 30
        test_days = self.test_months * 30
        step_days = self.step_months * 30

        if total_days < train_days + test_days:
            logger.error(f"Dati insufficienti: {total_days} giorni")
            return {"error": "Insufficient data"}

        logger.info(f"Walk-Forward: {self.train_months}m train / {self.test_months}m test / {self.step_months}m step")

        windows = []
        current = data_start
        while current + pd.Timedelta(days=train_days + test_days) <= data_end:
            windows.append({
                "train_start": current,
                "train_end": current + pd.Timedelta(days=train_days),
                "test_start": current + pd.Timedelta(days=train_days),
                "test_end": current + pd.Timedelta(days=train_days + test_days),
            })
            current += pd.Timedelta(days=step_days)

        logger.info(f"Windows: {len(windows)}")

        window_results = []
        all_oos_trades = []

        for i, w in enumerate(windows):
            logger.info(f"  Window {i+1}/{len(windows)}: {w['test_start'].date()} → {w['test_end'].date()}")

            sim = TradeSimulator(initial_balance=initial_balance, prop_rules=prop_rules, enforce_prop=False)

            for sym, df_full in data.items():
                df_test = df_full[(df_full.index >= w["test_start"]) & (df_full.index < w["test_end"])].copy()
                if len(df_test) < 100:
                    continue
                htf = htf_data.get(sym)
                htf_slice = htf[htf.index < w["test_end"]].copy() if htf is not None else None
                df_signals = strategy.generate_signals_batch(df_test, htf_slice)
                sim.run(df_signals, sym)

            metrics = calculate_metrics(sim.trades, sim)
            metrics["window"] = i + 1
            metrics["test_start"] = w["test_start"].strftime("%Y-%m-%d")
            metrics["test_end"] = w["test_end"].strftime("%Y-%m-%d")
            window_results.append(metrics)
            all_oos_trades.extend(sim.trades)

            logger.info(f"    {metrics.get('total_trades',0)} trades | WR {metrics.get('winrate_pct',0):.1f}% | ${metrics.get('total_pnl_usd',0):+,.2f}")

        oos_sim = TradeSimulator(initial_balance=initial_balance, prop_rules=prop_rules, enforce_prop=False)
        oos_sim.trades = all_oos_trades
        bal = initial_balance
        for t in all_oos_trades:
            bal += t["pnl_usd"]
        oos_sim.balance = bal

        profitable_w = sum(1 for w in window_results if w.get("total_pnl_usd", 0) > 0)
        consistency = (profitable_w / len(windows) * 100) if windows else 0

        return {
            "windows": window_results,
            "oos_aggregate": calculate_metrics(all_oos_trades, oos_sim),
            "total_windows": len(windows),
            "profitable_windows": profitable_w,
            "consistency_pct": round(consistency, 1),
            "all_oos_trades": all_oos_trades,
        }


class MonteCarloSimulation:
    def __init__(self, n_simulations=1000):
        self.n = n_simulations

    def run(self, trades, initial_balance, prop_rules):
        pnls = np.array([t["pnl_usd"] for t in trades])
        n_trades = len(pnls)

        target_pct = prop_rules.get("profit_target_pct")
        target_usd = (initial_balance * target_pct / 100) if target_pct else None
        max_total = initial_balance * prop_rules["max_total_loss_pct"] / 100

        max_dds, final_pnls = [], []
        violations = target_hit = 0

        for _ in range(self.n):
            shuffled = np.random.permutation(pnls)
            bal = initial_balance
            peak = initial_balance
            max_dd = 0

            for pnl in shuffled:
                bal += pnl
                if bal > peak: peak = bal
                dd = peak - bal
                if dd > max_dd: max_dd = dd

            max_dds.append((max_dd / peak * 100) if peak > 0 else 0)
            final_pnls.append(bal - initial_balance)
            if initial_balance - bal >= max_total: violations += 1
            if target_usd and bal - initial_balance >= target_usd: target_hit += 1

        dd = np.array(max_dds)
        fp = np.array(final_pnls)

        return {
            "n_simulations": self.n, "n_trades": n_trades,
            "pnl_mean": round(float(np.mean(fp)), 2),
            "pnl_median": round(float(np.median(fp)), 2),
            "pnl_5th": round(float(np.percentile(fp, 5)), 2),
            "pnl_95th": round(float(np.percentile(fp, 95)), 2),
            "dd_mean_pct": round(float(np.mean(dd)), 2),
            "dd_median_pct": round(float(np.median(dd)), 2),
            "dd_95th_pct": round(float(np.percentile(dd, 95)), 2),
            "dd_99th_pct": round(float(np.percentile(dd, 99)), 2),
            "prop_pass_rate": round((1 - violations / self.n) * 100, 1),
            "target_hit_rate": round(target_hit / self.n * 100, 1),
            "prob_profitable": round(sum(1 for p in fp if p > 0) / self.n * 100, 1),
        }


def print_walk_forward_report(results):
    print(f"\n{'═' * 80}\n  🔬 WALK-FORWARD ANALYSIS\n{'═' * 80}")
    print(f"  {'Window':<8} {'Period':<25} {'Trades':>7} {'WR%':>7} {'P&L $':>12} {'PF':>7}")
    print(f"  {'─' * 70}")

    for w in results["windows"]:
        e = "🟢" if w.get("total_pnl_usd", 0) > 0 else "🔴"
        print(f"  {e} {w['window']:<5} {w['test_start']} → {w['test_end']}  {w.get('total_trades',0):>6} "
              f"{w.get('winrate_pct',0):>6.1f}% {w.get('total_pnl_usd',0):>+11,.2f} {w.get('profit_factor',0):>6.2f}")

    oos = results["oos_aggregate"]
    c = results["consistency_pct"]
    ce = "🟢" if c >= 70 else ("🟡" if c >= 50 else "🔴")
    print(f"\n  OOS: {oos.get('total_trades',0)} trades | WR {oos.get('winrate_pct',0):.1f}% | ${oos.get('total_pnl_usd',0):+,.2f} | PF {oos.get('profit_factor',0):.2f}")
    print(f"  {ce} CONSISTENCY: {results['profitable_windows']}/{results['total_windows']} ({c}%)")

    if c >= 70 and oos.get("profit_factor", 0) > 1.0:
        print(f"  ✅ STRATEGIA ROBUSTA")
    elif c >= 50:
        print(f"  ⚠️ STRATEGIA MARGINALE")
    else:
        print(f"  ❌ NON ROBUSTA")
    print(f"{'═' * 80}\n")


def print_monte_carlo_report(r):
    print(f"\n{'═' * 80}\n  🎲 MONTE CARLO ({r['n_simulations']} sim × {r['n_trades']} trades)\n{'═' * 80}")
    print(f"  P&L:  5th=${r['pnl_5th']:+,.2f}  median=${r['pnl_median']:+,.2f}  mean=${r['pnl_mean']:+,.2f}  95th=${r['pnl_95th']:+,.2f}")
    print(f"  DD:   mean={r['dd_mean_pct']:.1f}%  median={r['dd_median_pct']:.1f}%  95th={r['dd_95th_pct']:.1f}%  99th={r['dd_99th_pct']:.1f}%")
    print(f"  Prob profitable: {r['prob_profitable']:.1f}%  |  Prop pass: {r['prop_pass_rate']:.1f}%  |  Target hit: {r['target_hit_rate']:.1f}%")

    if r["prop_pass_rate"] >= 70 and r["prob_profitable"] >= 80:
        print(f"  ✅ RISCHIO ACCETTABILE")
    elif r["prop_pass_rate"] >= 50:
        print(f"  ⚠️ RISCHIO MODERATO")
    else:
        print(f"  ❌ RISCHIO ELEVATO")
    print(f"{'═' * 80}\n")


def main():
    parser = argparse.ArgumentParser(description="Robustness Tester")
    parser.add_argument("--strategy", type=str, required=True)
    parser.add_argument("--symbol", type=str, default=None)
    parser.add_argument("--csv", type=str, default=None)
    parser.add_argument("--csv-tf", type=str, default="M1")
    parser.add_argument("--months", type=int, default=6)
    parser.add_argument("--wf-train", type=int, default=6)
    parser.add_argument("--wf-test", type=int, default=2)
    parser.add_argument("--wf-step", type=int, default=2)
    parser.add_argument("--monte-carlo", type=int, default=1000)
    parser.add_argument("--export", action="store_true")
    args = parser.parse_args()

    StrategyRegistry.discover()
    strategy = StrategyRegistry.get(args.strategy.upper())
    if not strategy:
        return

    strat_tf = strategy.timeframe()
    strat_symbols = [args.symbol.upper()] if args.symbol else strategy.symbols()
    htf_tf = strategy.htf_timeframe() or "H4"

    rules_map = {"FTMO": FTMO_RULES, "FUNDEDNEXT": FUNDEDNEXT_RULES}
    prop_rules = rules_map[ACTIVE_PROP][CURRENT_PHASE]
    initial_balance = prop_rules["account_size"]

    print()
    data_cache = {}
    htf_cache = {}

    if args.csv:
        logger.info(f"📁 CSV mode — {args.strategy}")
        if os.path.isdir(args.csv):
            for sym, fp in scan_csv_directory(args.csv).items():
                if args.symbol and sym != args.symbol.upper(): continue
                if sym not in [s.upper() for s in strat_symbols] and not args.symbol: continue
                df = load_csv_candles(fp, sym)
                if df is not None:
                    if args.csv_tf != strat_tf:
                        df = resample_to_timeframe(df, strat_tf)
                    data_cache[sym] = df
                    htf = resample_to_timeframe(df, htf_tf)
                    if len(htf) > 0: htf_cache[sym] = htf
        elif os.path.isfile(args.csv):
            sym = args.symbol.upper() if args.symbol else os.path.splitext(os.path.basename(args.csv))[0].upper().split("_")[0]
            df = load_csv_candles(args.csv, sym)
            if df is not None:
                if args.csv_tf != strat_tf:
                    df = resample_to_timeframe(df, strat_tf)
                data_cache[sym] = df
                htf = resample_to_timeframe(df, htf_tf)
                if len(htf) > 0: htf_cache[sym] = htf
    else:
        import MetaTrader5 as mt5
        if not connect_mt5(): sys.exit(1)
        for sym in strat_symbols:
            df = load_candles(sym, strat_tf, args.months)
            if df is not None: data_cache[sym] = df
            htf = load_candles(sym, htf_tf, args.months)
            if htf is not None: htf_cache[sym] = htf
        mt5.shutdown()

    if not data_cache:
        logger.error("Nessun dato"); sys.exit(1)

    logger.info(f"Loaded: {len(data_cache)} symbols")

    # Walk-Forward
    wf = WalkForwardAnalysis(args.wf_train, args.wf_test, args.wf_step)
    wf_results = wf.run(data_cache, htf_cache, strategy, prop_rules, initial_balance)

    if "error" not in wf_results:
        print_walk_forward_report(wf_results)

        if args.monte_carlo > 0 and wf_results.get("all_oos_trades"):
            mc = MonteCarloSimulation(args.monte_carlo)
            mc_results = mc.run(wf_results["all_oos_trades"], initial_balance, prop_rules)
            print_monte_carlo_report(mc_results)

        if args.export:
            os.makedirs("robustness_results", exist_ok=True)
            pd.DataFrame(wf_results["windows"]).to_csv(f"robustness_results/{args.strategy}_wf.csv", index=False)
            if wf_results.get("all_oos_trades"):
                pd.DataFrame(wf_results["all_oos_trades"]).to_csv(f"robustness_results/{args.strategy}_oos.csv", index=False)

    logger.info("✅ Robustness completato")


if __name__ == "__main__":
    main()
