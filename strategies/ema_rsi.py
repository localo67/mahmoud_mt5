"""
Strategie 2 : EMA Bounce + RSI (XAUUSD M5) — RECOMMANDEE

SELL : prix < EMA50 < EMA200 (tendance baissiere), prix remonte toucher EMA50,
       RSI etait > 60 puis repasse < 60
BUY  : prix > EMA50 > EMA200 (tendance haussiere), prix descend toucher EMA50,
       RSI etait < 40 puis repasse > 40

SL = 12 pips, TP = 24 pips (ratio 1:2)
Filtre : EMA200 M15
"""

import logging
import numpy as np
from typing import Optional

from strategies.base import BaseStrategy, Signal, ro, rh, rl, rc
from config import (
    S2_EMA_SHORT, S2_EMA_LONG,
    S2_RSI_PERIOD, S2_RSI_HIGH, S2_RSI_LOW,
    S2_SL_PIPS, S2_TP_PIPS,
)

logger = logging.getLogger(__name__)


class EmaRsiStrategy(BaseStrategy):
    """Strategie de rebond sur EMA avec confirmation RSI."""

    def __init__(self):
        super().__init__("Str2_EMA_RSI")
        self._prev_rsi: Optional[float] = None  # Pour detecter le croisement RSI

    async def evaluate(
        self,
        rates_m5: list,
        rates_m15: list,
        current_price: dict,
    ) -> Optional[Signal]:
        if len(rates_m5) < S2_EMA_LONG + 5 or len(rates_m15) < S2_EMA_LONG:
            return None

        closes_m5 = np.array([rc(r) for r in rates_m5])
        highs_m5 = np.array([rh(r) for r in rates_m5])
        lows_m5 = np.array([rl(r) for r in rates_m5])

        closes_m15 = np.array([rc(r) for r in rates_m15])

        # EMA M5
        ema50_m5 = self._ema(closes_m5, S2_EMA_SHORT)
        ema200_m5 = self._ema(closes_m5, S2_EMA_LONG)

        # EMA200 M15 pour filtre global
        ema200_m15 = self._ema(closes_m15, S2_EMA_LONG)

        # RSI actuel
        rsi_now = self._rsi(closes_m5, S2_RSI_PERIOD)

        bid = current_price["bid"]

        # --- BUY Signal ---
        buy_signal = self._check_buy(
            closes_m5, highs_m5, lows_m5, bid,
            ema50_m5, ema200_m5, ema200_m15, rsi_now,
        )
        if buy_signal:
            return buy_signal

        # --- SELL Signal ---
        sell_signal = self._check_sell(
            closes_m5, highs_m5, lows_m5, bid,
            ema50_m5, ema200_m5, ema200_m15, rsi_now,
        )
        if sell_signal:
            return sell_signal

        # Stocker le RSI pour le prochain cycle
        self._prev_rsi = rsi_now
        return None

    def _check_buy(
        self, closes, highs, lows, bid,
        ema50, ema200, ema200_m15, rsi_now,
    ) -> Optional[Signal]:
        """Verifie les conditions BUY (rebond haussier sur EMA50)."""

        # Filtre tendance M15
        if not self._trend_filter(bid, ema200_m15, "buy"):
            return None

        # Tendance haussiere M5 : prix > EMA50 > EMA200
        if not (bid > ema50 > ema200):
            return None

        # Prix proche de EMA50 (dans une zone de 5 pips)
        distance_ema50 = bid - ema50
        zone = self.pip_to_price(5, "buy")
        if distance_ema50 > zone:
            return None

        # Le prix doit venir d'au-dessus (pullback vers EMA50)
        # Verifier que le prix etait plus haut il y a 3 bougies
        if closes[-4] <= ema50:
            return None

        # RSI : etait < 40 (survente) et remonte
        prev_rsi = self._prev_rsi
        if prev_rsi is not None:
            # Condition : RSI etait sous S2_RSI_LOW et vient de passer au-dessus
            if prev_rsi < S2_RSI_LOW and rsi_now > S2_RSI_LOW:
                pass  # Signal ideal
            elif rsi_now <= S2_RSI_LOW:
                return None  # Toujours en survente, attendre
            elif rsi_now > 60:
                return None  # Trop etire
        else:
            # Premier passage, RSI doit etre en zone basse
            if rsi_now > S2_RSI_LOW + 10:
                return None

        # Signal confirme
        sl = ema50 - self.pip_to_price(S2_SL_PIPS, "buy")
        tp = bid + self.pip_to_price(S2_TP_PIPS, "buy")

        logger.info(
            f"Str2 BUY: ema50={ema50:.2f} ema200={ema200:.2f} "
            f"rsi={rsi_now:.1f} sl={sl:.2f} tp={tp:.2f}"
        )

        return Signal(
            direction="buy",
            sl_price=sl,
            tp_price=tp,
            strategy_name=self.name,
            metadata={
                "ema50": ema50,
                "ema200": ema200,
                "ema200_m15": ema200_m15,
                "rsi": rsi_now,
            },
        )

    def _check_sell(
        self, closes, highs, lows, bid,
        ema50, ema200, ema200_m15, rsi_now,
    ) -> Optional[Signal]:
        """Verifie les conditions SELL (rebond baissier sur EMA50)."""

        # Filtre tendance M15
        if not self._trend_filter(bid, ema200_m15, "sell"):
            return None

        # Tendance baissiere M5 : prix < EMA50 < EMA200
        if not (bid < ema50 < ema200):
            return None

        # Prix proche de EMA50 (dans une zone de 5 pips)
        distance_ema50 = ema50 - bid
        zone = self.pip_to_price(5, "sell")
        if distance_ema50 > zone:
            return None

        # Le prix doit venir d'en-dessous (pullback vers EMA50)
        if closes[-4] >= ema50:
            return None

        # RSI : etait > 60 (surachat) et redescend
        prev_rsi = self._prev_rsi
        if prev_rsi is not None:
            if prev_rsi > S2_RSI_HIGH and rsi_now < S2_RSI_HIGH:
                pass  # Signal ideal
            elif rsi_now >= S2_RSI_HIGH:
                return None  # Toujours en surachat
            elif rsi_now < 40:
                return None  # Trop etire
        else:
            if rsi_now < S2_RSI_HIGH - 10:
                return None

        # Signal confirme
        sl = ema50 + self.pip_to_price(S2_SL_PIPS, "sell")
        tp = bid - self.pip_to_price(S2_TP_PIPS, "sell")

        logger.info(
            f"Str2 SELL: ema50={ema50:.2f} ema200={ema200:.2f} "
            f"rsi={rsi_now:.1f} sl={sl:.2f} tp={tp:.2f}"
        )

        return Signal(
            direction="sell",
            sl_price=sl,
            tp_price=tp,
            strategy_name=self.name,
            metadata={
                "ema50": ema50,
                "ema200": ema200,
                "ema200_m15": ema200_m15,
                "rsi": rsi_now,
            },
        )
