"""
Configuration du bot de trading MT5 + IA.
Charge les variables d'environnement et definit les constantes.
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

# --- Variables d'environnement obligatoires ---

TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN", "")
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL: str = os.getenv(
    "OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free"
)
AUTHORIZED_CHAT_ID: int = int(os.getenv("AUTHORIZED_CHAT_ID", "0"))
MT5_LOGIN: int = int(os.getenv("MT5_LOGIN", "0"))
MT5_PASSWORD: str = os.getenv("MT5_PASSWORD", "")
MT5_SERVER: str = os.getenv("MT5_SERVER", "")


def validate_config() -> bool:
    """
    Verifie que toutes les variables d'environnement requises sont definies.
    Retourne True si valide, False sinon (avec messages d'erreur).
    """
    required = {
        "TELEGRAM_TOKEN": TELEGRAM_TOKEN,
        "OPENROUTER_API_KEY": OPENROUTER_API_KEY,
        "AUTHORIZED_CHAT_ID": AUTHORIZED_CHAT_ID,
        "MT5_LOGIN": MT5_LOGIN,
        "MT5_PASSWORD": MT5_PASSWORD,
        "MT5_SERVER": MT5_SERVER,
    }

    missing = [name for name, value in required.items() if not value]

    if missing:
        print(f" [CONFIG] Variables d'environnement manquantes : {', '.join(missing)}")
        print("   Copiez .env.example en .env et remplissez les valeurs.")
        return False

    return True


# --- Constantes de trading ---

DEFAULT_SYMBOL = "EURUSD"
DEFAULT_VOLUME = 0.01
DEVIATION_PIPS = 20
MAGIC_NUMBER = 20240601
MAX_RETRIES = 3

# --- Timeframes MT5 (en secondes pour copy_rates_from_pos) ---
TIMEFRAME_MAP = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
}

# --- Constantes d'automation ---

AUTOMATION_INTERVAL_SECONDS = 60   # Verification toutes les 60 secondes
AUTOMATION_TIMEFRAME = "M5"        # Timeframe pour les strategies
MA_SHORT_PERIOD = 20
MA_LONG_PERIOD = 50
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

# Symboles surveilles par l'automation
AUTOMATION_SYMBOLS = ["EURUSD", "GBPUSD", "XAUUSD"]

# =====================================================================
# XAUUSD AUTONOMOUS SCALPING BOT CONFIG
# =====================================================================

SYMBOL = os.getenv("BOT_SYMBOL", "XAUUSD")
VOLUME = float(os.getenv("BOT_VOLUME", "0.01"))
TIMEFRAME = "M5"
TREND_TIMEFRAME = "M15"
CANDLE_COUNT = 200  # Nombre de bougies a charger

# NY Session (UTC) — 9h-17h NY = 13h-21h UTC
NY_START_HOUR = int(os.getenv("NY_START_HOUR", "13"))
NY_END_HOUR = int(os.getenv("NY_END_HOUR", "21"))

# Risk Manager (no trade count limit, only P&L caps)
MAX_CONSECUTIVE_LOSSES = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "2"))
MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", "50.0"))
MAX_DAILY_PROFIT = float(os.getenv("MAX_DAILY_PROFIT", "100.0"))
STATE_FILE = os.getenv("STATE_FILE", "state.json")

# Strategy 1 — Breakout + Retest
S1_EMA = 200
S1_BREAKOUT_PIPS = 10
S1_SL_PIPS = 15
S1_TP_PIPS = 30

# Strategy 2 — EMA Bounce + RSI
S2_EMA_SHORT = 50
S2_EMA_LONG = 200
S2_RSI_PERIOD = 14
S2_RSI_HIGH = 60
S2_RSI_LOW = 40
S2_SL_PIPS = 12
S2_TP_PIPS = 24

# Strategy 3 — Engulfing + Trend
S3_SL_PIPS = 5
S3_TP_MIN_PIPS = 20
S3_TP_MAX_PIPS = 25

# Point value for XAUUSD (1 pip = 0.01, 1 lot = 1$ per 0.01 move -> 1 pip = 0.10$ for 0.01 lot)
# Actually: XAUUSD pip = 0.01, 1 standard lot = 1$ per pip, 0.01 lot = 0.01$ per pip
# For simplicity: 1 point in XAUUSD (0.01) = pip_value * volume
XAUUSD_PIP_VALUE = 0.01  # 1 pip = 0.01 in price for 0.01 lot = 0.01$ per pip

# =====================================================================
# IA TRADER CONFIG
# =====================================================================

NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
FMP_API_KEY = os.getenv("FMP_API_KEY", "")
NEWS_ENABLED = os.getenv("NEWS_ENABLED", "true").lower() == "true"

# IA decision thresholds
AI_MIN_CONFIDENCE = int(os.getenv("AI_MIN_CONFIDENCE", "60"))  # Score minimum
AI_SL_MIN_PIPS = int(os.getenv("AI_SL_MIN_PIPS", "3"))
AI_SL_MAX_PIPS = int(os.getenv("AI_SL_MAX_PIPS", "30"))
AI_RISK_REWARD_MIN = float(os.getenv("AI_RISK_REWARD_MIN", "1.5"))  # TP/SL min

# OpenRouter IA model for trading decisions
# Panel multi-modele (hierarchie: ULTRA decide, OWL verifie, LAGUNA check rapide, SUPER fallback)
AI_MODEL_PRIMARY = os.getenv("AI_MODEL_PRIMARY", "nvidia/nemotron-3-ultra-550b-a55b:free")
AI_MODEL_VALIDATOR = os.getenv("AI_MODEL_VALIDATOR", "openrouter/owl-alpha")
AI_MODEL_FAST = os.getenv("AI_MODEL_FAST", "poolside/laguna-m.1:free")
AI_MODEL_FALLBACK = os.getenv("AI_MODEL_FALLBACK", "nvidia/nemotron-3-super-120b-a12b:free")

# Multi-model validation mode
AI_PANEL_ENABLED = os.getenv("AI_PANEL_ENABLED", "false").lower() == "true"
AI_VETO_THRESHOLD = int(os.getenv("AI_VETO_THRESHOLD", "1"))  # Nb de votes contre pour annuler

# Spread filter (en points — 1 point = 0.001 sur XAUUSD chez la plupart des brokers)
MAX_SPREAD_POINTS = int(os.getenv("MAX_SPREAD_POINTS", "35"))

# Trailing stop
TRAILING_ACTIVATE_PIPS = int(os.getenv("TRAILING_ACTIVATE_PIPS", "10"))
TRAILING_DISTANCE_PIPS = int(os.getenv("TRAILING_DISTANCE_PIPS", "5"))
TRAILING_ENABLED = os.getenv("TRAILING_ENABLED", "true").lower() == "true"

# Position sizing adaptatif
RISK_PER_TRADE_PCT = float(os.getenv("RISK_PER_TRADE_PCT", "0.5"))  # % du capital risque par trade
POSITION_SIZING_ENABLED = os.getenv("POSITION_SIZING_ENABLED", "true").lower() == "true"

# Rapport quotidien
DAILY_REPORT_HOUR = int(os.getenv("DAILY_REPORT_HOUR", "21"))  # 21h UTC = 17h NY
