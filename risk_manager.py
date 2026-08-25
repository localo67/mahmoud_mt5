"""
Risk Manager : controle quotidien des risques.
Limite le nombre de trades, les pertes consecutives,
et les pertes/gains maximaux par jour.
Etat persiste dans un fichier JSON pour survivre aux crashs.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from config import (
    MAX_DAILY_LOSS,
    MAX_DAILY_PROFIT,
    STATE_FILE,
    RISK_PER_TRADE_PCT,
    POSITION_SIZING_ENABLED,
    VOLUME,
)

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Gere les limites de risque quotidiennes.
    L'etat est sauvegarde dans STATE_FILE apres chaque trade.
    """

    def __init__(self):
        self.trades_count: int = 0
        self.consecutive_losses: int = 0
        self.daily_pnl: float = 0.0
        self.blocked: bool = False
        self.block_reason: str = ""
        self.last_reset_date: str = ""

        self._load_or_reset()

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def check_trade_allowed(self) -> tuple[bool, str]:
        """
        Verifie si un nouveau trade est autorise.
        Retourne (autorise, raison).

        Verifie dans l'ordre :
        1. Reset quotidien si nouveau jour
        2. Compte bloque
        3. Perte journaliere max
        4. Gain journalier max
        """
        self._daily_reset_if_needed()

        if self.blocked:
            return False, f"Bloque : {self.block_reason}"

        if self.daily_pnl <= -MAX_DAILY_LOSS:
            self._block(f"Perte max/jour atteinte ({MAX_DAILY_LOSS}$)")
            return False, self.block_reason

        if self.daily_pnl >= MAX_DAILY_PROFIT:
            self._block(f"Gain max/jour atteint ({MAX_DAILY_PROFIT}$)")
            return False, self.block_reason

        return True, "OK"

    def record_trade_result(self, profit: float) -> None:
        """
        Enregistre le resultat d'un trade.

        Args:
            profit: Profit/perte en USD (positif = gain, negatif = perte)
        """
        self._daily_reset_if_needed()

        self.trades_count += 1
        self.daily_pnl += profit

        if profit < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        self._save()

        logger.info(
            f"Risk: trade #{self.trades_count} P&L={profit:+.2f}$ "
            f"daily={self.daily_pnl:+.2f}$ consec_losses={self.consecutive_losses}"
        )

    def get_status(self) -> str:
        """Retourne un resume pour Telegram."""
        self._daily_reset_if_needed()

        status = "BLOQUE" if self.blocked else "ACTIF"
        return (
            f"Risk Manager [{status}]\n"
            f"Trades aujourd'hui : {self.trades_count}\n"
            f"Pertes consecutives : {self.consecutive_losses}\n"
            f"P&L jour : {self.daily_pnl:+.2f}$ "
            f"(max perte: {MAX_DAILY_LOSS}$, max gain: {MAX_DAILY_PROFIT}$)"
            + (f"\nRaison blocage : {self.block_reason}" if self.blocked else "")
        )

    def get_context_for_ai(self) -> str:
        """Retourne un resume concis pour le prompt de l'IA."""
        self._daily_reset_if_needed()

        loss_left = MAX_DAILY_LOSS + self.daily_pnl if self.daily_pnl < 0 else MAX_DAILY_LOSS
        gain_left = max(0, MAX_DAILY_PROFIT - self.daily_pnl)

        return (
            f"Trades: {self.trades_count} | "
            f"Consec losses: {self.consecutive_losses} | "
            f"P&L: {self.daily_pnl:+.2f}$ | "
            f"Loss left: {loss_left:.2f}$ | "
            f"Gain left: {gain_left:.2f}$ | "
            f"{'BLOQUE' if self.blocked else 'OK'}"
        )

    def calculate_position_size(self, account_equity: float, atr: float) -> float:
        """
        Calcule le volume optimal base sur le risque par trade et l'ATR.

        Formule: volume = (equity * risk_pct) / (ATR * lot_value)
        Pour XAUUSD: lot_value = 1$ par point pour 1 lot, donc 0.01$ pour 0.01 lot
        Exemple: equity=1000$, risk=0.5% → risk=5$. ATR=0.15 → volume = 5 / (0.15 * 100) = 0.033

        Retourne un volume arrondi au step MT5 (0.01) et clampé entre 0.01 et 1.0.
        """
        if not POSITION_SIZING_ENABLED or atr <= 0:
            return VOLUME

        risk_amount = account_equity * (RISK_PER_TRADE_PCT / 100.0)
        # ATR en dollars par lot standard: ATR * 100 (1 lot = 100 oz, 1$ par point)
        atr_dollar_per_lot = atr * 100.0
        if atr_dollar_per_lot <= 0:
            return VOLUME

        raw_volume = risk_amount / atr_dollar_per_lot
        # Arrondir au step 0.01 et clamper
        volume = max(0.01, min(1.0, round(raw_volume * 100) / 100))

        logger.info(
            f"Position sizing: equity={account_equity:.0f}$ "
            f"risk={RISK_PER_TRADE_PCT}% ({risk_amount:.2f}$) "
            f"ATR={atr:.3f}$ → volume={volume:.2f}"
        )
        return volume

    def update_real_pnl(self, profit: float) -> None:
        """Met a jour le P&L quotidien avec le vrai profit/perte d'un trade ferme."""
        self._daily_reset_if_needed()
        self.daily_pnl += profit
        logger.info(f"Risk: P&L reel mis a jour: {profit:+.2f}$ → daily={self.daily_pnl:+.2f}$")
        self._save()

    def reset(self) -> None:
        """Reinitialise manuellement l'etat quotidien."""
        self.trades_count = 0
        self.consecutive_losses = 0
        self.daily_pnl = 0.0
        self.blocked = False
        self.block_reason = ""
        self.last_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._save()
        logger.info("Risk: reinitialisation manuelle")

    # ------------------------------------------------------------------
    # Interne
    # ------------------------------------------------------------------

    def _daily_reset_if_needed(self) -> None:
        """Reinitialise l'etat si on a change de jour."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.last_reset_date != today:
            logger.info(f"Risk: nouveau jour ({today}), reinitialisation")
            self.trades_count = 0
            self.consecutive_losses = 0
            self.daily_pnl = 0.0
            self.blocked = False
            self.block_reason = ""
            self.last_reset_date = today
            self._save()

    def _block(self, reason: str) -> None:
        """Bloque le trading pour le reste de la journee."""
        self.blocked = True
        self.block_reason = reason
        self._save()
        logger.warning(f"Risk: TRADING BLOQUE — {reason}")

    def _save(self) -> None:
        """Sauvegarde l'etat dans le fichier JSON."""
        state = {
            "trades_count": self.trades_count,
            "consecutive_losses": self.consecutive_losses,
            "daily_pnl": self.daily_pnl,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
            "last_reset_date": self.last_reset_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        }
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.error(f"Risk: erreur sauvegarde state.json : {e}")

    def _load_or_reset(self) -> None:
        """Charge l'etat depuis le fichier JSON, ou cree un etat vierge."""
        if not os.path.exists(STATE_FILE):
            self._daily_reset_if_needed()
            return

        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)

            self.trades_count = state.get("trades_count", 0)
            self.consecutive_losses = state.get("consecutive_losses", 0)
            self.daily_pnl = state.get("daily_pnl", 0.0)
            self.blocked = state.get("blocked", False)
            self.block_reason = state.get("block_reason", "")
            self.last_reset_date = state.get("last_reset_date", "")

            # Reset si nouveau jour
            self._daily_reset_if_needed()

            logger.info(
                f"Risk: etat charge — trades={self.trades_count} "
                f"pnl={self.daily_pnl:+.2f}$ blocked={self.blocked}"
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Risk: state.json corrompu ({e}), reinitialisation")
            self._daily_reset_if_needed()
