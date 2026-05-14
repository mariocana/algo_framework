"""
Strategy Registry — auto-discovers and manages all strategies.

Strategies are loaded from the strategies/ directory.
Each file that contains a BaseStrategy subclass is auto-registered.
"""

import importlib
import inspect
import logging
import os
import sys
from typing import Optional

from core.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


class StrategyRegistry:
    """Discovers, registers, and instantiates strategies."""

    _strategies: dict[str, type] = {}

    @classmethod
    def discover(cls, strategies_dir: str = "strategies"):
        """
        Auto-discover all strategies in the strategies/ directory.
        Any class that subclasses BaseStrategy gets registered.
        """
        cls._strategies.clear()

        if not os.path.isdir(strategies_dir):
            logger.error(f"Strategies directory not found: {strategies_dir}")
            return

        # Add parent dir to path so imports work
        parent = os.path.dirname(os.path.abspath(strategies_dir))
        if parent not in sys.path:
            sys.path.insert(0, parent)

        for filename in sorted(os.listdir(strategies_dir)):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue

            module_name = f"strategies.{filename[:-3]}"
            try:
                module = importlib.import_module(module_name)

                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        inspect.isclass(attr)
                        and issubclass(attr, BaseStrategy)
                        and attr is not BaseStrategy
                    ):
                        # Instantiate temporarily to get the name
                        try:
                            instance = attr.__new__(attr)
                            name = instance.name
                            cls._strategies[name] = attr
                            logger.info(f"  ✅ Registered: {name} (from {filename})")
                        except Exception:
                            cls._strategies[attr.__name__] = attr
                            logger.info(f"  ✅ Registered: {attr.__name__} (from {filename})")

            except Exception as e:
                logger.warning(f"  ⚠️ Failed to load {filename}: {e}")

        logger.info(f"Registry: {len(cls._strategies)} strategies loaded")

    @classmethod
    def get(cls, name: str, config: dict = None, mt5_handler=None) -> Optional[BaseStrategy]:
        """Get an instantiated strategy by name."""
        name = name.upper()
        strategy_class = cls._strategies.get(name)
        if strategy_class is None:
            logger.error(f"Strategy '{name}' not found. Available: {list(cls._strategies.keys())}")
            return None
        return strategy_class(config=config, mt5_handler=mt5_handler)

    @classmethod
    def list_strategies(cls) -> list[str]:
        """List all registered strategy names."""
        return list(cls._strategies.keys())

    @classmethod
    def print_catalog(cls):
        """Print all available strategies with their configs."""
        print(f"\n{'═' * 60}")
        print(f"  📋 STRATEGY CATALOG — {len(cls._strategies)} strategies")
        print(f"{'═' * 60}")

        for name, strat_class in sorted(cls._strategies.items()):
            try:
                instance = strat_class()
                cfg = instance.default_config
                tf = instance.timeframe()
                syms = instance.symbols()
                sym_str = ', '.join(syms[:5])
                if len(syms) > 5:
                    sym_str += f" (+{len(syms)-5} more)"

                print(f"\n  📈 {name}")
                print(f"     Timeframe: {tf}")
                print(f"     Symbols:   {sym_str}")
                print(f"     Config:    {len(cfg)} parameters")
            except Exception as e:
                print(f"\n  ⚠️ {name} — error loading: {e}")

        print(f"\n{'═' * 60}\n")
