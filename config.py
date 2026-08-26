"""
Configuration du bot de trading MT5 + IA.
Charge les variables d'environnement et definit les constantes.
"""

import os
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
TRADING_MODE: str = os.getenv("TRADING_MODE", "off").lower()
VALID_TRADING_MODES = frozenset({"off", "shadow", "demo", "live"})
if TRADING_MODE not in VALID_TRADING_MODES:
    raise ValueError(
        f"TRADING_MODE invalide: {TRADING_MODE!r}; "
        f"valeurs autorisees: {', '.join(sorted(VALID_TRADING_MODES))}"
    )


def validate_config() -> bool:
    """
    Verifie que toutes les variables d'environnement requises sont definies.
    Retourne True si valide, False sinon (avec messages d'erreur).
    """
    required = {
        "TELEGRAM_TOKEN": TELEGRAM_TOKEN,
        "OPENROUTER_API_KEY": OPENROUTER_API_KEY,
        "AUTHORIZED_CHAT_ID": AUTHORIZED_CHAT_ID,
    }
    if TRADING_MODE in {"shadow", "demo", "live"}:
        required.update({
            "MT5_LOGIN": MT5_LOGIN,
            "MT5_PASSWORD": MT5_PASSWORD,
            "MT5_SERVER": MT5_SERVER,
        })

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

# =====================================================================
# Runtime XAUUSD (session New York)
# =====================================================================

SYMBOL = os.getenv("BOT_SYMBOL", "XAUUSD")
VOLUME = float(os.getenv("BOT_VOLUME", "0.01"))
TIMEFRAME = "M5"
TREND_TIMEFRAME = "M15"
CANDLE_COUNT = 200

# Heures locales America/New_York (l'heure d'ete/hiver est geree automatiquement)
NY_START_HOUR = int(os.getenv("NY_START_HOUR", "9"))
NY_END_HOUR = int(os.getenv("NY_END_HOUR", "17"))

MAX_CONSECUTIVE_LOSSES = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "2"))
MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", "50.0"))
STATE_FILE = os.getenv("STATE_FILE", "state.json")

NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
FMP_API_KEY = os.getenv("FMP_API_KEY", "")
NEWS_ENABLED = os.getenv("NEWS_ENABLED", "true").lower() == "true"

# Spread max en points (1 point = 0.01 sur XAUUSD chez beaucoup de courtiers)
MAX_SPREAD_POINTS = int(os.getenv("MAX_SPREAD_POINTS", "35"))

RISK_PER_TRADE_PCT = float(os.getenv("RISK_PER_TRADE_PCT", "0.5"))
DAILY_REPORT_HOUR = int(os.getenv("DAILY_REPORT_HOUR", "21"))
