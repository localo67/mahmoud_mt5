"""
Collecteur de donnees Financial Modeling Prep (FMP).
Enrichit le bot avec: forex news, prix or COMEX, taux US, indicateurs eco.
Tous les endpoints utilises sont gratuits (250 req/j).
"""

import logging
from datetime import datetime, timezone

from config import FMP_API_KEY

logger = logging.getLogger(__name__)

FMP_BASE = "https://financialmodelingprep.com/stable"


class FMPCollector:
    """Collecte les donnees FMP pour enrichir le contexte IA."""

    def __init__(self):
        self._cache: dict = {}
        self._cache_times: dict[str, float] = {}
        self._cache_ttl: float = 300.0  # 5 min

    async def get_forex_news(self, limit: int = 5) -> list[dict]:
        """News forex depuis FMP."""
        cache_key = "forex_news"
        if self._use_cache(cache_key):
            return self._cache.get(cache_key, [])[:limit]

        try:
            import httpx
            url = f"{FMP_BASE}/news/forex-latest"
            params = {"page": 0, "limit": limit, "apikey": FMP_API_KEY}

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params=params)

            if resp.status_code != 200:
                logger.debug(f"FMP forex news: HTTP {resp.status_code}")
                return self._cache.get(cache_key, [])

            articles = resp.json()
            headlines = []
            for a in articles:
                headlines.append({
                    "title": a.get("title", ""),
                    "source": "FMP",
                    "time": a.get("publishedDate", ""),
                    "symbols": a.get("symbols", []),
                })

            self._cache[cache_key] = headlines
            self._cache_times[cache_key] = datetime.now(timezone.utc).timestamp()
            logger.info(f"FMP: {len(headlines)} forex news collectees")
            return headlines

        except Exception as e:
            logger.debug(f"FMP forex news error: {e}")
            return self._cache.get(cache_key, [])

    async def get_gold_price(self) -> dict | None:
        """Prix or futures COMEX (GCUSD)."""
        cache_key = "gold_price"
        if self._use_cache(cache_key):
            return self._cache.get(cache_key)

        try:
            import httpx
            url = f"{FMP_BASE}/quote?symbol=GCUSD&apikey={FMP_API_KEY}"

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)

            if resp.status_code != 200:
                return None

            data = resp.json()
            if data:
                quote = data[0]
                result = {
                    "symbol": "GCUSD",
                    "price": quote.get("price"),
                    "change": quote.get("change"),
                    "change_percent": quote.get("changesPercentage"),
                    "day_high": quote.get("dayHigh"),
                    "day_low": quote.get("dayLow"),
                    "volume": quote.get("volume"),
                }
                self._cache[cache_key] = result
                self._cache_times[cache_key] = datetime.now(timezone.utc).timestamp()
                return result
        except Exception as e:
            logger.debug(f"FMP gold price error: {e}")
        return self._cache.get(cache_key)

    async def get_treasury_rates(self) -> dict | None:
        """Taux du tresor US (2 ans, 10 ans, 30 ans)."""
        cache_key = "treasury"
        if self._use_cache(cache_key):
            return self._cache.get(cache_key)

        try:
            import httpx
            url = f"{FMP_BASE}/treasury-rates?apikey={FMP_API_KEY}"

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)

            if resp.status_code != 200:
                return None

            data = resp.json()
            if data:
                latest = data[0]
                result = {
                    "date": latest.get("date"),
                    "year2": latest.get("year2"),
                    "year10": latest.get("year10"),
                    "year30": latest.get("year30"),
                }
                self._cache[cache_key] = result
                self._cache_times[cache_key] = datetime.now(timezone.utc).timestamp()
                return result
        except Exception as e:
            logger.debug(f"FMP treasury error: {e}")
        return self._cache.get(cache_key)

    def format_for_ai(self, forex_news: list[dict], gold_quote: dict | None,
                      treasury: dict | None) -> str:
        """Formate toutes les donnees FMP pour le prompt IA."""
        lines = []

        if gold_quote:
            lines.append(
                f" Or COMEX: {gold_quote.get('price', '?')}$ "
                f"({gold_quote.get('change_percent', '?')}%) "
                f"High:{gold_quote.get('day_high', '?')} Low:{gold_quote.get('day_low', '?')}"
            )

        if treasury:
            lines.append(
                f" Taux US: 2Y={treasury.get('year2', '?')}% "
                f"10Y={treasury.get('year10', '?')}% "
                f"30Y={treasury.get('year30', '?')}%"
            )

        if forex_news:
            lines.append(f" News Forex ({len(forex_news)}):")
            for n in forex_news:
                lines.append(f"  - {n['title']}")

        return "\n".join(lines) if lines else "FMP: aucune donnee disponible."

    def _use_cache(self, key: str) -> bool:
        now = datetime.now(timezone.utc).timestamp()
        return now - self._cache_times.get(key, 0) < self._cache_ttl
