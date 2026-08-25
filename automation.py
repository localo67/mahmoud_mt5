"""
Moteur d'automation : assemble le bot autonome IA-first.
"""

import logging
from telegram.ext import Application

from risk_manager import RiskManager
from news_filter import NewsFilter
from news_collector import NewsCollector
from fmp_collector import FMPCollector
from ai_trader import AITrader
from strategy_engine import StrategyEngine
from strategies.breakout import BreakoutRetestStrategy
from strategies.ema_rsi import EmaRsiStrategy
from strategies.engulfing import EngulfingStrategy
from config import AUTHORIZED_CHAT_ID

logger = logging.getLogger(__name__)


class AutomationEngine:
    """Wrapper qui assemble et lance le bot autonome XAUUSD."""

    def __init__(self, application: Application, mt5_client):
        self.app = application
        self.mt5 = mt5_client
        self.enabled: bool = False

        # Composants
        self.risk_mgr = RiskManager()
        self.news_filter = NewsFilter(fail_safe=True)  # Mode securise
        self.news_collector = NewsCollector()
        self.fmp = FMPCollector()
        self.ai_trader = AITrader()

        # Strategies (guidelines pour l'IA)
        strategies = [
            EmaRsiStrategy(),
            BreakoutRetestStrategy(),
            EngulfingStrategy(),
        ]

        # Orchestrateur IA-first
        self.engine = StrategyEngine(
            application=application,
            mt5_client=mt5_client,
            risk_manager=self.risk_mgr,
            news_filter=self.news_filter,
            news_collector=self.news_collector,
            fmp_collector=self.fmp,
            ai_trader=self.ai_trader,
            strategies=strategies,
        )
        self.engine.enabled = False

        self.engine.chat_id = AUTHORIZED_CHAT_ID

    async def run(self) -> None:
        logger.info("AutomationEngine: bot IA autonome XAUUSD lance")
        await self.engine.run()

    async def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if self.engine:
            self.engine.enabled = enabled
        logger.info(f"AutomationEngine: {'ON' if enabled else 'OFF'}")

    def get_risk_status(self) -> str:
        return self.risk_mgr.get_status()

    def reset_risk(self) -> str:
        self.risk_mgr.reset()
        return self.risk_mgr.get_status()
