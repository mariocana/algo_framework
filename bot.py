"""
Prop Trading Bot — Live execution using Strategy Registry.

Usage:
    python bot.py --strategy BB_RSI_SCALP
    python bot.py --strategy BB_RSI_AGGRO
    python bot.py --status
    python bot.py --close-all
    python bot.py --list
"""

import argparse
import logging
import time
import signal as sig_module
import sys
from datetime import datetime, timezone

from config import (
    SCAN_INTERVAL_SECONDS, LOG_LEVEL, ACTIVE_PROP, CURRENT_PHASE, RISK,
)
from core.registry import StrategyRegistry
from mt5_handler import MT5Handler
from risk_manager import RiskManager
from session_manager import SessionManager
from telegram_notifier import TelegramNotifier

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s │ %(name)-18s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("prop_bot.log", mode="a"),
    ],
)
logger = logging.getLogger("bot")


class PropTradingBot:
    def __init__(self, strategy_name: str):
        self.mt5 = MT5Handler()

        # Discover and load strategy
        StrategyRegistry.discover()
        self.strategy = StrategyRegistry.get(strategy_name, mt5_handler=self.mt5)
        if not self.strategy:
            logger.critical(f"Strategy '{strategy_name}' not found")
            sys.exit(1)

        self.risk = RiskManager(self.mt5)
        self.session = SessionManager()
        self.telegram = TelegramNotifier()

        self._running = False
        self._cycle_count = 0
        self._last_status = None

        logger.info(f"Strategy: {self.strategy.name}")
        logger.info(f"Symbols: {', '.join(self.strategy.symbols())}")
        logger.info(f"Timeframe: {self.strategy.timeframe()}")

    def start(self):
        logger.info(f"🤖 Bot starting — {self.strategy.name}")

        if not self.mt5.connect():
            logger.critical("Cannot connect to MT5")
            return

        self.risk.initialize()
        account = self.mt5.get_account_info()
        self.telegram.send_startup(account)

        sig_module.signal(sig_module.SIGINT, self._shutdown)
        sig_module.signal(sig_module.SIGTERM, self._shutdown)

        self._running = True
        logger.info(f"Running — scan every {SCAN_INTERVAL_SECONDS}s")

        while self._running:
            try:
                self._cycle()
            except Exception as e:
                logger.exception(f"Cycle error: {e}")
                self.telegram.send_risk_alert(f"Error: {str(e)[:300]}")
            time.sleep(SCAN_INTERVAL_SECONDS)

    def _shutdown(self, *args):
        self._running = False
        self.telegram.send_shutdown()
        self.mt5.disconnect()
        sys.exit(0)

    def _cycle(self):
        self._cycle_count += 1

        if not self.mt5.ensure_connected():
            return

        emergency = self.risk.emergency_check()
        if emergency:
            self.telegram.send_emergency(emergency)
            if "Total drawdown BREACHED" in emergency:
                self._running = False
            return

        self.risk.manage_open_positions()

        if self.session.should_close_before_weekend():
            positions = self.mt5.get_open_positions()
            if positions:
                closed = self.mt5.close_all_positions()
                self.telegram.send_risk_alert(f"Weekend close: {closed} positions")
            return

        session_ok, reason = self.session.is_trading_allowed()
        if not session_ok:
            return

        # Scan using strategy
        signals = self.strategy.scan_all()

        for signal in signals:
            self._process_signal(signal)

        if self._cycle_count % 240 == 0:  # ~2h
            status = self.risk.get_full_status()
            self.telegram.send_status_report(status)

    def _process_signal(self, signal):
        logger.info(f"📡 Signal: {signal}")

        existing = self.mt5.get_open_positions(signal.symbol)
        if existing:
            return

        lots = self.risk.calculate_lot_size(signal.symbol, signal.sl_distance_points)
        allowed, reason = self.risk.can_open_trade(signal.symbol, lots)
        if not allowed:
            logger.warning(f"  Blocked: {reason}")
            return

        result = self.mt5.open_position(
            symbol=signal.symbol, direction=signal.direction,
            lots=lots, sl=signal.sl, tp=signal.tp,
            comment=f"Bot_{signal.strategy}",
        )

        if result:
            self.risk.record_trading_day()
            self.telegram.send_trade_opened(result, signal.reason)
        else:
            self.telegram.send_risk_alert(f"Execution failed: {signal.symbol}")


def main():
    parser = argparse.ArgumentParser(description="Prop Trading Bot")
    parser.add_argument("--strategy", type=str, default=None)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--close-all", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    if args.list:
        StrategyRegistry.discover()
        StrategyRegistry.print_catalog()
        return

    if not args.strategy and not (args.status or args.close_all):
        logger.error("Specifica --strategy. Usa --list per le disponibili.")
        return

    strategy_name = (args.strategy or "BB_RSI_SCALP").upper()

    if args.status or args.close_all:
        mt5 = MT5Handler()
        if not mt5.connect():
            sys.exit(1)
        risk = RiskManager(mt5)
        risk.initialize()
        telegram = TelegramNotifier()

        if args.status:
            status = risk.get_full_status()
            telegram.send_status_report(status)
        elif args.close_all:
            closed = mt5.close_all_positions()
            telegram.send_risk_alert(f"Manual close: {closed} positions")

        mt5.disconnect()
    else:
        bot = PropTradingBot(strategy_name)
        bot.start()


if __name__ == "__main__":
    main()
