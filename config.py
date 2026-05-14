"""
Prop Trading Bot — Configuration
Supports: FTMO, FundedNext
Platform: MetaTrader 5 (CFD)

IMPORTANT: Fill in your credentials and adjust settings before running.
"""

# ============================================================
# METATRADER 5 CONNECTION
# ============================================================
# ============================================================
# PROP FIRM SELECTION
# ============================================================
# Options: "FTMO" or "FUNDEDNEXT"
ACTIVE_PROP = "FTMO"
 
# Current phase: "CHALLENGE", "VERIFICATION", "FUNDED"
CURRENT_PHASE = "CHALLENGE"
 
# ============================================================
# PROP FIRM RULES — FTMO
# ============================================================
 
FTMO_RULES = {
    "CHALLENGE": {
        "account_size": 100_000,        # Account size in USD
        "profit_target_pct": 10.0,      # 10% profit target
        "max_daily_loss_pct": 5.0,      # 5% max daily loss
        "max_total_loss_pct": 10.0,     # 10% max total loss
        "min_trading_days": 4,          # Minimum 4 trading days
        "max_trading_days": None,       # No time limit (unlimited)
        "max_leverage": 100,            # 1:100
        "weekend_holding": True,        # Allowed
        "news_trading": True,           # Allowed
    },
    "VERIFICATION": {
        "account_size": 100_000,
        "profit_target_pct": 5.0,       # 5% profit target
        "max_daily_loss_pct": 5.0,
        "max_total_loss_pct": 10.0,
        "min_trading_days": 4,
        "max_trading_days": None,
        "max_leverage": 100,
        "weekend_holding": True,
        "news_trading": True,
    },
    "FUNDED": {
        "account_size": 100_000,
        "profit_target_pct": None,      # No target — just trade
        "max_daily_loss_pct": 5.0,
        "max_total_loss_pct": 10.0,
        "min_trading_days": 4,
        "max_trading_days": None,
        "max_leverage": 100,
        "weekend_holding": True,
        "news_trading": True,
    },
}
 
# ============================================================
# PROP FIRM RULES — FUNDEDNEXT
# ============================================================
 
FUNDEDNEXT_RULES = {
    "CHALLENGE": {
        "account_size": 100_000,
        "profit_target_pct": 10.0,      # 10% Phase 1
        "max_daily_loss_pct": 5.0,
        "max_total_loss_pct": 10.0,
        "min_trading_days": 5,          # Min 5 calendar days
        "max_trading_days": 30,         # 30 days limit
        "max_leverage": 100,
        "weekend_holding": False,       # Must close before weekend
        "news_trading": False,          # Restricted on major news
    },
    "VERIFICATION": {
        "account_size": 100_000,
        "profit_target_pct": 5.0,
        "max_daily_loss_pct": 5.0,
        "max_total_loss_pct": 10.0,
        "min_trading_days": 5,
        "max_trading_days": 60,
        "max_leverage": 100,
        "weekend_holding": False,
        "news_trading": False,
    },
    "FUNDED": {
        "account_size": 100_000,
        "profit_target_pct": None,
        "max_daily_loss_pct": 5.0,
        "max_total_loss_pct": 10.0,
        "min_trading_days": 5,
        "max_trading_days": None,
        "max_leverage": 100,
        "weekend_holding": False,
        "news_trading": False,
    },
}
 
# ============================================================
# RISK MANAGEMENT SETTINGS
# ============================================================
 
RISK = {
    # ── Risk per trade: depends on active strategy ──
    # BB_RSI_SCALP (management):  1.0%
    # BB_RSI_AGGRO (challenge):   2.0%
    "risk_per_trade_pct": 2.0,       # ⚡ 2% for challenge pass
 
    # Max simultaneous open positions
    "max_open_positions": 3,
 
    # Max total exposure as % of balance
    "max_exposure_pct": 5.0,
 
    # Daily loss safety buffer — bot stops before hitting prop limit
    "daily_loss_buffer": 0.80,
 
    # Total loss safety buffer
    "total_loss_buffer": 0.80,
 
    # Trailing stop settings
    "trailing_stop_enabled": True,
    "trailing_stop_pct": 0.5,
 
    # Break-even settings
    "breakeven_enabled": True,
    "breakeven_trigger_pct": 0.3,
    "breakeven_offset_pips": 2,
 
    # Max spread allowed to open a trade (in points)
    "max_spread_points": 20,         # Più stretto per M1 scalping
}
 
# ============================================================
# TRADING STRATEGY SETTINGS
# ============================================================
 
STRATEGY = {
    # Strategy to use:
    # "BB_RSI_SCALP"  = conservative (for funded management)
    # "BB_RSI_AGGRO"  = aggressive (for challenge pass)
    # "EMA_CROSS", "RSI_MEAN_REVERSION", "BREAKOUT" = other strategies
    "active_strategy": "BB_RSI_AGGRO",
 
    # ── Symbol Selection ──
    "symbols": "AUTO",
    "symbol_filters": {
        "categories": ["forex"],
        "spread_max": 30,
        "tradeable_only": True,
        "exclude_contains": ["_"],
    },
 
    # Timeframes
    "entry_timeframe": "M5",
    "trend_timeframe": "H1",
    "htf_timeframe": "H4",
 
    # EMA Cross settings
    "ema_fast": 9,
    "ema_slow": 21,
    "ema_trend": 200,
 
    # RSI settings
    "rsi_period": 14,
    "rsi_oversold": 30,
    "rsi_overbought": 70,
 
    # Breakout settings
    "breakout_lookback": 20,
    "breakout_atr_multiplier": 1.5,
 
    # ATR for SL/TP
    "atr_period": 14,
    "sl_atr_multiplier": 1.5,
    "tp_atr_multiplier": 3.0,
 
    # ════════════════════════════════════════════════════
    # 📈 BB_RSI_SCALP — GESTIONE FUNDED (conservative)
    # ════════════════════════════════════════════════════
    "bb_rsi": {
        "bb_period": 40,
        "bb_std_dev": 2.0,
        "rsi_period": 5,
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "adx_period": 14,
        "adx_max": 25,
        "swing_lookback": 10,
        "sl_buffer_pips": 3,
        "entry_timeframe": "M5",
        # WHITELIST gestione — testata e confermata
        "symbols": [
            "GBPUSD",   # WR 59.4% | PF 1.39 | +$10,854
            "EURUSD",   # WR 72.0% | PF 2.35 | +$9,709
            "AUDCAD",   # WR 72.7% | PF 2.12 | +$7,208
            "GBPCHF",   # WR 78.6% | PF 3.16 | +$6,719
            "AUDNZD",   # WR 100%  | PF ∞    | +$5,741
            "USDCHF",   # WR 77.8% | PF 2.34 | +$2,709
        ],
    },
 
    # ════════════════════════════════════════════════════
    # ⚡ BB_RSI_AGGRO — PASSAGGIO CHALLENGE (aggressive)
    # ════════════════════════════════════════════════════
    "bb_rsi_aggro": {
        "bb_period": 20,                 # BB più strette → più segnali
        "bb_std_dev": 2.0,               # 2σ standard
        "rsi_period": 3,                 # RSI ultra-reattivo
        "rsi_oversold": 25,              # Soglie più estreme → segnali più puliti
        "rsi_overbought": 75,
        "adx_period": 14,
        "adx_max": 30,                   # Tollera più trend (più segnali)
        "swing_lookback": 5,             # SL più stretto → RR migliore
        "sl_buffer_pips": 2,             # Buffer minore
        "entry_timeframe": "M5",         # M5 (M1 non disponibile su FTMO demo 6 mesi)
        "min_rr": 0.7,                   # RR minimo più permissivo
        # AUTO = testa tutti i forex del broker
        "symbols": [    
            "GBPCHF",   
            "AUDCAD",   
            "AUDNZD",   
            "EURUSD",   
            "CADCHF",  
            "EURCHF",
            "USDCAD",  
            "NZDUSD",
        ],
    },
}
 
# ============================================================
# TRADING SESSIONS (UTC)
# ============================================================
 
SESSIONS = {
    "london_open": {"start": "07:00", "end": "11:00"},
    "new_york_open": {"start": "12:00", "end": "16:00"},
    "overlap": {"start": "12:00", "end": "15:00"},
    # Set which sessions to trade
    "active_sessions": ["london_open", "new_york_open"],
}
 
# ============================================================
# SCHEDULER
# ============================================================
 
# How often the bot checks for signals (seconds)
SCAN_INTERVAL_SECONDS = 30
 
# Log level: "DEBUG", "INFO", "WARNING"
LOG_LEVEL = "INFO"