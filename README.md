# 🤖 Algo Trading Framework

Framework modulare per sviluppo, backtest e deployment di strategie di trading.

## Struttura

```
algo_framework/
├── core/                          # Framework core (non toccare)
│   ├── base_strategy.py           # Classe base — ogni strategia la estende
│   ├── indicators.py              # Libreria indicatori condivisa
│   └── registry.py                # Auto-discovery delle strategie
│
├── strategies/                    # ← LE TUE STRATEGIE VANNO QUI
│   ├── _template.py               # Template — copialo per creare nuove strategie
│   ├── bb_rsi_scalp.py            # BB+RSI conservativa (gestione funded)
│   └── bb_rsi_aggro.py            # BB+RSI aggressiva (challenge pass)
│
├── data/                          # Dati CSV (Tickstory, Dukascopy, etc.)
│   └── EURUSD_M1.csv
│
├── backtester.py                  # Backtest engine
├── robustness.py                  # Walk-Forward + Monte Carlo
├── pipeline.py                    # Full pipeline automatico
├── bot.py                         # Bot live MT5
├── config.py                      # Configurazione globale
└── mt5_handler.py                 # Connessione MetaTrader 5
```

## Creare una Nuova Strategia

```bash
# 1. Copia il template
cp strategies/_template.py strategies/mia_strategia.py

# 2. Modifica il file: nome, config, logica

# 3. Testa
python pipeline.py --strategy MIA_STRATEGIA --csv ./data/ --csv-tf M1

# Fatto! Nessuna altra modifica necessaria.
```

## Comandi

```bash
# Backtest singolo
python backtester.py --strategy BB_RSI_SCALP --csv ./data/ --csv-tf M1

# Robustness test
python robustness.py --strategy BB_RSI_AGGRO --csv ./data/ --csv-tf M1

# Pipeline completa (backtest + walk-forward + monte carlo)
python pipeline.py --strategy BB_RSI_AGGRO --csv ./data/ --csv-tf M1 --export

# Lista strategie disponibili
python -c "from core.registry import StrategyRegistry; StrategyRegistry.discover(); StrategyRegistry.print_catalog()"

# Bot live
python bot.py --strategy BB_RSI_SCALP
```

## Indicatori Disponibili

Tutti in `core/indicators.py`, importabili con `from core import indicators as ind`:

| Indicatore | Funzione | Parametri |
|-----------|----------|-----------|
| EMA | `ind.ema(series, period)` | period |
| SMA | `ind.sma(series, period)` | period |
| RSI | `ind.rsi(series, period)` | period |
| ATR | `ind.atr(df, period)` | period |
| Bollinger Bands | `ind.bollinger_bands(series, period, std)` | period, std_dev |
| ADX | `ind.adx(df, period)` | period |
| MACD | `ind.macd(series, fast, slow, signal)` | fast, slow, signal |
| Stochastic | `ind.stochastic(df, k, d)` | k_period, d_period |
| VWAP | `ind.vwap(df)` | — |
| Ichimoku | `ind.ichimoku(df)` | tenkan, kijun, senkou_b |
| Supertrend | `ind.supertrend(df, period, mult)` | period, multiplier |
| Pivot Points | `ind.pivots(df)` | — |
