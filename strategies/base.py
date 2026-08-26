"""
Interface commune pour toutes les strategies de trading.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import numpy as np

from core.indicators import atr as core_atr
from core.indicators import ema as core_ema
from core.indicators import rsi as core_rsi


# Helpers compatibilite Windows/Linux: les rates MT5 sont des tuples sur Windows
def ro(r): return r.open if hasattr(r, 'open') else r[1]
def rh(r): return r.high  if hasattr(r, 'high')  else r[2]
def rl(r): return r.low   if hasattr(r, 'low')   else r[3]
def rc(r): return r.close if hasattr(r, 'close') else r[4]


@dataclass
class Signal:
    """Signal de trading genere par une strategie."""
    direction: str        # "buy" ou "sell"
    sl_price: float       # Stop Loss en prix absolu
    tp_price: float       # Take Profit en prix absolu
    strategy_name: str    # Nom de la strategie pour les logs
    metadata: dict        # Infos supplementaires (ex: {"ema50": 2650.0, "rsi": 65.2})


class BaseStrategy(ABC):
    """Classe de base pour toutes les strategies."""

    def __init__(self, name: str):
        self.name = name
        self._last_signal_time: float = 0.0  # Pour eviter les signaux repetes

    @abstractmethod
    async def evaluate(
        self,
        rates_m5: list,
        rates_m15: list,
        current_price: dict,
    ) -> Optional[Signal]:
        """
        Evalue la strategie et retourne un Signal ou None.

        Args:
            rates_m5: Liste de rates MT5 en M5 (objets avec open, high, low, close, etc.)
            rates_m15: Liste de rates MT5 en M15
            current_price: dict avec "bid" et "ask"

        Returns:
            Signal si conditions remplies, None sinon.
        """
        ...

    # ------------------------------------------------------------------
    # Utilitaires communs
    # ------------------------------------------------------------------

    def _ema(self, closes: np.ndarray, period: int) -> float:
        """Calcule l'EMA (implementation unique du noyau)."""
        return core_ema(closes, period)

    def _sma(self, closes: np.ndarray, period: int) -> float:
        """Calcule la SMA (Simple Moving Average)."""
        return float(np.mean(closes[-period:]))

    def _rsi(self, closes: np.ndarray, period: int = 14) -> float:
        """Calcule le RSI (implementation unique du noyau)."""
        return core_rsi(closes, period)

    def _atr(self, rates: list, period: int = 14) -> float:
        ohlc = [(ro(r), rh(r), rl(r), rc(r)) for r in rates]
        return core_atr(ohlc, period)

    def _recent_high(self, highs: np.ndarray, lookback: int = 20, exclude_last: int = 1) -> float:
        """Plus haut recent (exclut les dernieres bougies)."""
        return float(np.max(highs[-(lookback + exclude_last):-exclude_last]))

    def _recent_low(self, lows: np.ndarray, lookback: int = 20, exclude_last: int = 1) -> float:
        """Plus bas recent (exclut les dernieres bougies)."""
        return float(np.min(lows[-(lookback + exclude_last):-exclude_last]))

    def _is_bullish_candle(self, open_: float, close: float) -> bool:
        return close > open_

    def _is_bearish_candle(self, open_: float, close: float) -> bool:
        return close < open_

    def _body_size(self, open_: float, close: float) -> float:
        return abs(close - open_)

    def _upper_wick(self, open_: float, close: float, high: float) -> float:
        return high - max(open_, close)

    def _lower_wick(self, open_: float, close: float, low: float) -> float:
        return min(open_, close) - low

    @staticmethod
    def _point() -> float:
        """Valeur d'un point pour XAUUSD (0.01)."""
        return 0.01

    def _trend_filter(self, price: float, ema200_m15: float, direction: str) -> bool:
        """
        Filtre de tendance EMA200 M15:
        - price > EMA200 → BUY only
        - price < EMA200 → SELL only
        """
        if direction == "buy":
            return price > ema200_m15
        else:
            return price < ema200_m15

    def pip_to_price(self, pips: int, direction: str) -> float:
        """Convertit des pips en ecart de prix XAUUSD."""
        points = pips * self._point()
        return points
