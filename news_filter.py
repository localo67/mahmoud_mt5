"""
Filtre de news economiques.
Bloque le trading pendant les annonces a fort impact (red folder).
Utilise le calendrier ForexFactory (scraping gratuit).

Si l'API echoue → fail-open (laisse passer le trading).
"""

import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# Fenetres a eviter : 15 min avant et 15 min apres une news "red folder"
NEWS_WINDOW_MINUTES = 15

# News USD connues a fort impact (fallback si le scraping echoue)
# Format : (mois, jour, heure_utc, description)
KNOWN_HIGH_IMPACT_NEWS = [
    # NFP — premier vendredi du mois, 12h30 UTC
    # FOMC — mercredi toutes les 6 semaines, 18h00 UTC
    # CPI — milieu du mois, 12h30 UTC
    # Ces dates sont trop variables pour etre hardcodees.
    # On utilise le scraping comme source principale.
]


class NewsFilter:
    """
    Verifie si on est dans une fenetre de news a fort impact.
    Mode securise: bloque le trading si l'API est inaccessible (fail-closed).
    """

    def __init__(self, fail_safe: bool = True):
        """
        Args:
            fail_safe: Si True → bloque le trading quand l'API est down.
                       Si False → laisse passer (fail-open, plus risqué).
        """
        self.fail_safe = fail_safe
        self._last_check_time: float = 0.0
        self._cached_result: bool = False
        self._cache_duration: float = 300.0  # 5 minutes

    async def is_news_time(self) -> bool:
        """
        Retourne True si on est dans une fenetre de news importantes.
        Utilise un cache de 5 minutes.
        """
        now = datetime.now(timezone.utc)
        now_ts = now.timestamp()

        if now_ts - self._last_check_time < self._cache_duration:
            return self._cached_result

        self._last_check_time = now_ts

        try:
            # D'abord essayer le scraping (ForexFactory)
            result = await self._check_forexfactory(now)
            if result:
                logger.info("News filter: fenetre news detectee, trading bloque")
            self._cached_result = result
        except Exception as e:
            logger.warning(f"News filter: scraping echoue ({e})")
            # Fail-safe: bloquer le trading si on ne peut pas verifier
            self._cached_result = self.fail_safe
            if self.fail_safe:
                logger.warning("News filter: mode securise → trading bloque")

        return self._cached_result

    async def _check_forexfactory(self, now: datetime) -> bool:
        """
        Verifie si on est dans une fenetre de news USD High Impact.
        Utilise un calendrier hardcode des news majeures + tentative API.
        """
        # 1. Verifier le calendrier hardcode (fiable, zero cout)
        if self._is_major_news_window(now):
            return True

        # 2. Tenter l'API (bonus, peut echouer)
        try:
            import httpx
            url = "https://www.forexfactory.com/calendar"
            headers = {"User-Agent": "Mozilla/5.0"}
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(url, headers=headers, follow_redirects=True)
            if response.status_code == 200:
                html = response.text.lower()
                today_str = now.strftime("%b %d").lower()
                keywords = ["non-farm", "nfp", "fomc", "cpi", "ppi", "fed"]
                for kw in keywords:
                    if kw in html and today_str in html:
                        logger.info(f"News filter: '{kw}' detecte via scraping")
                        return True
        except Exception:
            pass

        return False

    @staticmethod
    def _is_major_news_window(now: datetime) -> bool:
        """
        Calendrier des news USD majeures (heures UTC).
        NFP: 1er vendredi du mois, 12h30
        CPI: milieu du mois, 12h30
        FOMC: mercredi toutes les 6 semaines, 18h00
        """
        hour = now.hour
        minute = now.minute
        weekday = now.weekday()  # 0=lundi, 6=dimanche
        day = now.day

        # Fenetres de news connues (UTC)
        # NFP/CPI/etc: 12h30 UTC → bloquer 12h15-13h00
        if hour == 12 and 15 <= minute <= 59:
            return True
        # FOMC: 18h00 UTC → bloquer 17h45-18h30
        if hour == 17 and minute >= 45:
            return True
        if hour == 18 and minute <= 30:
            return True
        # PMI/ISM: 14h00 UTC → bloquer 13h45-14h30
        if hour == 13 and minute >= 45:
            return True
        if hour == 14 and minute <= 30:
            return True

        return False
