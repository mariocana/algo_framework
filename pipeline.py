"""
Full Pipeline — Backtest + Robustness using Strategy Registry.

Usage:
    python pipeline.py --strategy BB_RSI_AGGRO --csv ./data/ --csv-tf M1
    python pipeline.py --strategy BB_RSI_SCALP --months 6
    python pipeline.py --list
"""

import argparse
import os
import sys
import time
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pipeline")


def main():
    parser = argparse.ArgumentParser(description="Full Pipeline")
    parser.add_argument("--strategy", type=str, default=None)
    parser.add_argument("--csv", type=str, default=None)
    parser.add_argument("--csv-tf", type=str, default="M1")
    parser.add_argument("--symbol", type=str, default=None)
    parser.add_argument("--months", type=int, default=6)
    parser.add_argument("--wf-train", type=int, default=6)
    parser.add_argument("--wf-test", type=int, default=2)
    parser.add_argument("--wf-step", type=int, default=2)
    parser.add_argument("--monte-carlo", type=int, default=1000)
    parser.add_argument("--no-prop", action="store_true")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--skip-backtest", action="store_true")
    parser.add_argument("--skip-robustness", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    if args.list:
        from core.registry import StrategyRegistry
        StrategyRegistry.discover()
        StrategyRegistry.print_catalog()
        return

    if not args.strategy:
        logger.error("Specifica --strategy. Usa --list per le disponibili.")
        return

    strategy = args.strategy.upper()
    start_time = time.time()

    width = 70
    print(f"\n{'█' * width}")
    print(f"█{'':^{width-2}}█")
    print(f"█{f'  🚀  FULL PIPELINE — {strategy}':^{width-2}}█")
    print(f"█{'':^{width-2}}█")
    print(f"{'█' * width}\n")

    data_src = f"CSV: {args.csv}" if args.csv else f"MT5 ({args.months}m)"
    print(f"  Strategy:     {strategy}")
    print(f"  Data:         {data_src}")
    print(f"  Symbol:       {args.symbol or 'all (from strategy config)'}")
    print()

    # Build common args
    common = []
    if args.csv:
        common.extend(["--csv", args.csv, "--csv-tf", args.csv_tf])
    else:
        common.extend(["--months", str(args.months)])
    if args.symbol:
        common.extend(["--symbol", args.symbol])
    if args.export:
        common.append("--export")

    # ── Phase 1: Backtest ──
    if not args.skip_backtest:
        print(f"{'─' * 60}\n  FASE 1: BACKTEST\n{'─' * 60}\n")

        cmd = [sys.executable, "backtester.py", "--strategy", strategy] + common
        if args.no_prop:
            cmd.append("--no-prop")
        os.system(" ".join(cmd))

        if not args.no_prop:
            print(f"\n{'─' * 60}\n  FASE 2: BACKTEST (no-prop)\n{'─' * 60}\n")
            cmd_np = [sys.executable, "backtester.py", "--strategy", strategy, "--no-prop"] + common
            os.system(" ".join(cmd_np))

    # ── Phase 2: Robustness ──
    if not args.skip_robustness:
        print(f"\n{'─' * 60}\n  FASE 3: WALK-FORWARD + MONTE CARLO\n{'─' * 60}\n")

        cmd = [
            sys.executable, "robustness.py", "--strategy", strategy,
            "--wf-train", str(args.wf_train),
            "--wf-test", str(args.wf_test),
            "--wf-step", str(args.wf_step),
            "--monte-carlo", str(args.monte_carlo),
        ] + common
        os.system(" ".join(cmd))

    # ── Final ──
    elapsed = time.time() - start_time
    m, s = int(elapsed // 60), int(elapsed % 60)

    print(f"\n{'█' * width}")
    print(f"█{f'  ✅  PIPELINE COMPLETATA — {m}m {s}s':^{width-2}}█")
    print(f"{'█' * width}\n")

    print(f"  Prossimi passi:")
    print(f"  • WF Consistency > 70% → strategia robusta")
    print(f"  • MC Prop pass > 70% → rischio accettabile")
    print(f"  • Se OK → python bot.py --strategy {strategy}")
    print(f"  • Se NO → ottimizza o cambia strategia")
    print()


if __name__ == "__main__":
    main()
