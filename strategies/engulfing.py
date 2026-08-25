"""
Strategie 3 : Engulfing + Trend (XAUUSD M5)

SELL : tendance baissiere (2 derniers plus hauts descendants),
       chandelier engulfing baissier (corps couvre le corps precedent)
BUY  : tendance haussiere (2 derniers plus bas ascendants),
       chandelier engulfing haussier

SL = 5 pips au-dessus/dessous du chandelier, TP = 20-25 pips
Filtre : EMA200 M15
"""

import logging
import numpy as np
from typing import Optional

from strategies.base import BaseStrategy, Signal, ro, rh, rl, rc
from config import S3_SL_PIPS, S3_TP_MIN_PIPS, S2_EMA_LONG

logger = logging.getLogger(__name__)


class EngulfingStrategy(BaseStrategy):
    """Strategie de chandelier engulfing avec tendance."""

    def __init__(self):
        super().__init__("Str3_Engulfing")

    async def evaluate(
        self,
        rates_m5: list,
        rates_m15: list,
        current_price: dict,
    ) -> Optional[Signal]:
        if len(rates_m5) < 22 or len(rates_m15) < S2_EMA_LONG:
            return None

        closes_m5 = np.array([rc(r) for r in rates_m5])
        highs_m5 = np.array([rh(r) for r in rates_m5])
        lows_m5 = np.array([rl(r) for r in rates_m5])
        opens_m5 = np.array([ro(r) for r in rates_m5])

        closes_m15 = np.array([rc(r) for r in rates_m15])

        # EMA200 M15
        ema200_m15 = self._ema(closes_m15, S2_EMA_LONG)

        bid = current_price["bid"]

        # Detecter engulfing sur la derniere bougie fermee
        # Derniere bougie fermee = index -2 (la -1 est en cours)
        prev_open = opens_m5[-2]
        prev_close = closes_m5[-2]
        prev_high = highs_m5[-2]
        prev_low = lows_m5[-2]

        # Bougie d'avant (pour comparer)
        before_open = opens_m5[-3]
        before_close = closes_m5[-3]
        before_high = highs_m5[-3]
        before_low = lows_m5[-3]

        # --- BUY Signal (Engulfing haussier) ---
        buy_signal = self._check_buy(
            bid, ema200_m15,
            prev_open, prev_close, prev_high, prev_low,
            before_open, before_close, before_high, before_low,
            highs_m5, lows_m5,
        )
        if buy_signal:
            return buy_signal

        # --- SELL Signal (Engulfing baissier) ---
        sell_signal = self._check_sell(
            bid, ema200_m15,
            prev_open, prev_close, prev_high, prev_low,
            before_open, before_close, before_high, before_low,
            highs_m5, lows_m5,
        )
        if sell_signal:
            return sell_signal

        return None

    def _check_buy(
        self, bid, ema200_m15,
        prev_open, prev_close, prev_high, prev_low,
        before_open, before_close, before_high, before_low,
        highs, lows,
    ) -> Optional[Signal]:
        """Verifie engulfing haussier en tendance haussiere."""

        # Filtre tendance M15
        if not self._trend_filter(bid, ema200_m15, "buy"):
            return None

        # Tendance haussiere : 2 derniers plus bas ascendants
        recent_low_1 = self._recent_low(lows, lookback=10, exclude_last=5)
        recent_low_2 = self._recent_low(lows, lookback=20, exclude_last=10)
        if recent_low_1 <= recent_low_2:
            return None

        # Engulfing haussier :
        # - Bougie precedente etait baissiere (before)
        # - Derniere bougie est haussiere (prev)
        # - Le corps de prev couvre le corps de before
        if not self._is_bearish_candle(before_open, before_close):
            return None
        if not self._is_bullish_candle(prev_open, prev_close):
            return None

        prev_body = self._body_size(prev_open, prev_close)
        before_body = self._body_size(before_open, before_close)

        if prev_body <= before_body:
            return None

        # Le corps de la bougie haussiere doit couvrir :
        # open prev < close before ET close prev > open before
        if prev_open > before_close or prev_close < before_open:
            return None

        # Signal confirme — entree a la cloture de la bougie engulfing
        entry = prev_close
        sl = prev_low - self.pip_to_price(S3_SL_PIPS, "buy")
        tp = entry + self.pip_to_price(S3_TP_MIN_PIPS, "buy")

        logger.info(
            f"Str3 BUY: engulfing haussier entry={entry:.2f} "
            f"sl={sl:.2f} tp={tp:.2f}"
        )

        return Signal(
            direction="buy",
            sl_price=sl,
            tp_price=tp,
            strategy_name=self.name,
            metadata={
                "entry": entry,
                "prev_body": prev_body,
                "before_body": before_body,
                "ema200_m15": ema200_m15,
            },
        )

    def _check_sell(
        self, bid, ema200_m15,
        prev_open, prev_close, prev_high, prev_low,
        before_open, before_close, before_high, before_low,
        highs, lows,
    ) -> Optional[Signal]:
        """Verifie engulfing baissier en tendance baissiere."""

        # Filtre tendance M15
        if not self._trend_filter(bid, ema200_m15, "sell"):
            return None

        # Tendance baissiere : 2 derniers plus hauts descendants
        recent_high_1 = self._recent_high(highs, lookback=10, exclude_last=5)
        recent_high_2 = self._recent_high(highs, lookback=20, exclude_last=10)
        if recent_high_1 >= recent_high_2:
            return None

        # Engulfing baissier :
        # - Bougie precedente etait haussiere (before)
        # - Derniere bougie est baissiere (prev)
        # - Le corps de prev couvre le corps de before
        if not self._is_bullish_candle(before_open, before_close):
            return None
        if not self._is_bearish_candle(prev_open, prev_close):
            return None

        prev_body = self._body_size(prev_open, prev_close)
        before_body = self._body_size(before_open, before_close)

        if prev_body <= before_body:
            return None

        # Le corps de la bougie baissiere doit couvrir
        if prev_open < before_close or prev_close > before_open:
            return None

        # Signal confirme
        entry = prev_close
        sl = prev_high + self.pip_to_price(S3_SL_PIPS, "sell")
        tp = entry - self.pip_to_price(S3_TP_MIN_PIPS, "sell")

        logger.info(
            f"Str3 SELL: engulfing baissier entry={entry:.2f} "
            f"sl={sl:.2f} tp={tp:.2f}"
        )

        return Signal(
            direction="sell",
            sl_price=sl,
            tp_price=tp,
            strategy_name=self.name,
            metadata={
                "entry": entry,
                "prev_body": prev_body,
                "before_body": before_body,
                "ema200_m15": ema200_m15,
            },
        )
