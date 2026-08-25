"""
Strategie 1 : Breakout + Retest (XAUUSD M5)

BUY : prix > EMA200, casse un plus haut + fermeture 5min au-dessus de 10 pips,
      retrace pour tester le niveau casse, chandelier de rejet haussier
SELL : inverse

SL = 15 pips, TP = 30 pips (ratio 1:2)
Filtre : EMA200 M15
"""

import logging
import numpy as np
from typing import Optional

from strategies.base import BaseStrategy, Signal, ro, rh, rl, rc
from config import S1_EMA, S1_BREAKOUT_PIPS, S1_SL_PIPS, S1_TP_PIPS

logger = logging.getLogger(__name__)


class BreakoutRetestStrategy(BaseStrategy):
    """Strategie de breakout avec retest du niveau casse."""

    def __init__(self):
        super().__init__("Str1_Breakout")

    async def evaluate(
        self,
        rates_m5: list,
        rates_m15: list,
        current_price: dict,
    ) -> Optional[Signal]:
        if len(rates_m5) < 22 or len(rates_m15) < S1_EMA:
            return None

        # Extraire les donnees
        closes_m5 = np.array([rc(r) for r in rates_m5])
        highs_m5 = np.array([rh(r) for r in rates_m5])
        lows_m5 = np.array([rl(r) for r in rates_m5])
        opens_m5 = np.array([ro(r) for r in rates_m5])

        closes_m15 = np.array([rc(r) for r in rates_m15])

        # EMA200 M5
        ema200_m5 = self._ema(closes_m5, S1_EMA)
        # EMA200 M15 pour filtre de tendance
        ema200_m15 = self._ema(closes_m15, S1_EMA)

        bid = current_price["bid"]
        breakout_pips_price = self.pip_to_price(S1_BREAKOUT_PIPS, "buy")

        # --- BUY Signal ---
        buy_signal = await self._check_buy(
            closes_m5, highs_m5, lows_m5, opens_m5,
            bid, ema200_m5, ema200_m15, breakout_pips_price,
        )
        if buy_signal:
            return buy_signal

        # --- SELL Signal ---
        sell_signal = await self._check_sell(
            closes_m5, highs_m5, lows_m5, opens_m5,
            bid, ema200_m5, ema200_m15, breakout_pips_price,
        )
        if sell_signal:
            return sell_signal

        return None

    async def _check_buy(
        self, closes, highs, lows, opens, bid, ema200_m5, ema200_m15, breakout_price
    ) -> Optional[Signal]:
        """Verifie les conditions BUY (Breakout haussier + retest)."""

        # Filtre tendance M15
        if not self._trend_filter(bid, ema200_m15, "buy"):
            return None

        # Prix doit etre au-dessus de EMA200 M5
        if bid <= ema200_m5:
            return None

        # Chercher un breakout recent (dernieres 10 bougies)
        recent_high = self._recent_high(highs, lookback=20, exclude_last=3)
        breakout_level = recent_high

        # Condition : une bougie a casse le plus haut et ferme au-dessus
        breakout_detected = False
        for i in range(-5, -1):  # 5 dernieres bougies fermees
            if closes[i] > breakout_level + breakout_price:
                breakout_detected = True
                break

        if not breakout_detected:
            return None

        # Retest : le prix est revenu pres du niveau casse
        distance_to_level = abs(bid - breakout_level)
        if distance_to_level > self.pip_to_price(5, "buy"):  # Max 5 pips du niveau
            return None

        # Derniere bougie : chandelier de rejet haussier
        last_open = opens[-1]
        last_close = closes[-1]
        last_low = lows[-1]
        last_high = highs[-1]

        # Rejet : meche basse > corps, cloture proche du haut
        body = self._body_size(last_open, last_close)
        lower_wick = self._lower_wick(last_open, last_close, last_low)
        upper_wick = self._upper_wick(last_open, last_close, last_high)

        if lower_wick < body * 1.5:
            return None

        if last_close <= last_open:
            return None  # Pas haussier

        # Signal confirme
        sl = bid - self.pip_to_price(S1_SL_PIPS, "buy")
        tp = bid + self.pip_to_price(S1_TP_PIPS, "buy")

        logger.info(
            f"Str1 BUY: breakout={breakout_level:.2f} ema200={ema200_m5:.2f} "
            f"sl={sl:.2f} tp={tp:.2f}"
        )

        return Signal(
            direction="buy",
            sl_price=sl,
            tp_price=tp,
            strategy_name=self.name,
            metadata={
                "breakout_level": breakout_level,
                "ema200_m5": ema200_m5,
                "ema200_m15": ema200_m15,
            },
        )

    async def _check_sell(
        self, closes, highs, lows, opens, bid, ema200_m5, ema200_m15, breakout_price
    ) -> Optional[Signal]:
        """Verifie les conditions SELL (Breakout baissier + retest)."""

        # Filtre tendance M15
        if not self._trend_filter(bid, ema200_m15, "sell"):
            return None

        # Prix doit etre en-dessous de EMA200 M5
        if bid >= ema200_m5:
            return None

        # Chercher un breakdown recent
        recent_low = self._recent_low(lows, lookback=20, exclude_last=3)
        breakdown_level = recent_low

        # Condition : une bougie a casse le plus bas et ferme en-dessous
        breakdown_detected = False
        for i in range(-5, -1):
            if closes[i] < breakdown_level - breakout_price:
                breakdown_detected = True
                break

        if not breakdown_detected:
            return None

        # Retest : le prix est remonte pres du niveau
        distance_to_level = abs(bid - breakdown_level)
        if distance_to_level > self.pip_to_price(5, "sell"):
            return None

        # Derniere bougie : chandelier de rejet baissier
        last_open = opens[-1]
        last_close = closes[-1]
        last_high = highs[-1]
        last_low = lows[-1]

        body = self._body_size(last_open, last_close)
        upper_wick = self._upper_wick(last_open, last_close, last_high)
        lower_wick = self._lower_wick(last_open, last_close, last_low)

        if upper_wick < body * 1.5:
            return None

        if last_close >= last_open:
            return None  # Pas baissier

        # Signal confirme
        sl = bid + self.pip_to_price(S1_SL_PIPS, "sell")
        tp = bid - self.pip_to_price(S1_TP_PIPS, "sell")

        logger.info(
            f"Str1 SELL: breakdown={breakdown_level:.2f} ema200={ema200_m5:.2f} "
            f"sl={sl:.2f} tp={tp:.2f}"
        )

        return Signal(
            direction="sell",
            sl_price=sl,
            tp_price=tp,
            strategy_name=self.name,
            metadata={
                "breakdown_level": breakdown_level,
                "ema200_m5": ema200_m5,
                "ema200_m15": ema200_m15,
            },
        )
