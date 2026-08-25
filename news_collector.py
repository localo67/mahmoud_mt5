"""
Collecteur de news pour le bot de trading.
Utilise NewsAPI (gratuit) pour recuperer les titres economiques
pertinents pour XAUUSD.
"""

import logging
from datetime import datetime, timezone, timedelta

from config import NEWS_API_KEY, NEWS_ENABLED

logger = logging.getLogger(__name__)

# Mots-cles pour filtrer les news pertinentes
XAUUSD_KEYWORDS = [
    "gold", "xau", "xauusd",
    "fed", "federal reserve", "powell",
    "inflation", "cpi", "ppi",
    "interest rate", "monetary policy",
    "geopolitical", "middle east", "ukraine",
    "dollar", "usd", "dxy",
    "central bank", "ecb",
    "nfp", "nonfarm", "unemployment",
    "gdp", "recession",
    "safe haven",
]


class NewsCollector:
    """
    Collecte les titres d'actualites economiques via NewsAPI.
    Fallback: retourne une liste vide si l'API est inaccessible.
    """

    def __init__(self):
        self._cache: list[dict] = []
        self._last_fetch: float = 0.0
        self._cache_ttl: float = 300.0  # 5 minutes

    async def get_headlines(self, max_results: int = 5) -> list[dict]:
        """
        Retourne les derniers titres pertinents pour XAUUSD.

        Returns:
            list[dict]: [{"title": "...", "source": "...", "time": "..."}, ...]
        """
        now = datetime.now(timezone.utc).timestamp()

        # Utiliser le cache si valide
        if now - self._last_fetch < self._cache_ttl:
            return self._cache[:max_results]

        self._last_fetch = now

        if not NEWS_ENABLED or not NEWS_API_KEY:
            self._cache = []
            return []

        try:
            headlines = await self._fetch_newsapi(max_results)
            self._cache = headlines
            return headlines
        except Exception as e:
            logger.debug(f"NewsCollector: echec fetch ({e})")
            return self._cache  # Retourne le vieux cache

    async def _fetch_newsapi(self, max_results: int) -> list[dict]:
        """Interroge l'API NewsAPI.org."""
        try:
            import httpx

            # Chercher les news des dernieres 2 heures
            query = " OR ".join(XAUUSD_KEYWORDS[:10])
            url = "https://newsapi.org/v2/everything"

            params = {
                "q": query,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": max_results,
                "apiKey": NEWS_API_KEY,
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params)

            if response.status_code != 200:
                logger.debug(f"NewsAPI returned {response.status_code}: {response.text[:200]}")
                return []

            data = response.json()
            articles = data.get("articles", [])

            headlines = []
            for art in articles:
                headlines.append({
                    "title": art.get("title", ""),
                    "source": art.get("source", {}).get("name", "Unknown"),
                    "time": art.get("publishedAt", ""),
                    "url": art.get("url", ""),
                })

            if headlines:
                logger.info(f"NewsCollector: {len(headlines)} titres collectes")

            return headlines

        except ImportError:
            logger.debug("NewsCollector: httpx non disponible")
            return []
        except Exception as e:
            logger.debug(f"NewsCollector: erreur API ({e})")
            return []

    async def analyze_sentiment(self, headlines: list[dict]) -> list[dict]:
        """Analyse le sentiment de chaque titre avec FinBERT (local si dispo)."""
        if not headlines:
            return []

        try:
            from transformers import pipeline

            # Charger FinBERT une seule fois (lazy)
            if not hasattr(self, '_finbert'):
                logger.info("NewsCollector: chargement FinBERT...")
                self._finbert = pipeline(
                    "text-classification",
                    model="ProsusAI/finbert",
                    max_length=512,
                    truncation=True,
                )

            for h in headlines:
                try:
                    result = self._finbert(h['title'])[0]
                    # FinBERT: positive/neutral/negative
                    label = result['label'].lower()
                    score = result['score']
                    if label == 'positive':
                        h['sentiment'] = score
                    elif label == 'negative':
                        h['sentiment'] = -score
                    else:
                        h['sentiment'] = 0.0
                except Exception:
                    h['sentiment'] = 0.0

        except ImportError:
            # FinBERT non installe → sentiment neutre
            for h in headlines:
                h['sentiment'] = 0.0
        except Exception as e:
            logger.debug(f"FinBERT error: {e}")
            for h in headlines:
                h['sentiment'] = 0.0

        return headlines

    def format_for_ai(self, headlines: list[dict]) -> str:
        """Formate les titres pour le prompt IA."""
        if not headlines:
            return "Aucune news recente disponible."

        lines = []
        for h in headlines:
            # Formater le temps relatif
            try:
                pub_time = datetime.fromisoformat(h["time"].replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                delta = now - pub_time
                if delta < timedelta(minutes=5):
                    time_str = "a l'instant"
                elif delta < timedelta(hours=1):
                    time_str = f"il y a {int(delta.total_seconds() / 60)} min"
                elif delta < timedelta(hours=3):
                    time_str = f"il y a {int(delta.total_seconds() / 3600)}h"
                else:
                    time_str = pub_time.strftime("%H:%M")
            except Exception:
                time_str = "?"

            sent = h.get('sentiment', 0)
            sent_str = f" [{sent:+.1f}]" if sent != 0 else ""
            lines.append(f"-{sent_str} \"{h['title']}\" ({h['source']}, {time_str})")

        return "\n".join(lines)
