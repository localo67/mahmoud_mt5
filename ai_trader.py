"""
AI Trader — Panel multi-modele hierarchique.
ULTRA 550B (decide) → OWL (verifie) → LAGUNA (check rapide) → Execute/WAIT
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from openai import AsyncOpenAI

from config import (
    OPENROUTER_API_KEY,
    AI_MODEL_PRIMARY,
    AI_MODEL_VALIDATOR,
    AI_MODEL_FAST,
    AI_MODEL_FALLBACK,
    AI_PANEL_ENABLED,
    AI_VETO_THRESHOLD,
    AI_MIN_CONFIDENCE,
    AI_SL_MIN_PIPS,
    AI_SL_MAX_PIPS,
    AI_RISK_REWARD_MIN,
    SYMBOL,
)

logger = logging.getLogger(__name__)


class AITrader:
    """
    Panel IA multi-modele pour decisions de trading.
    Architecture: Primary(decide) → Validator(verify) → Fast(sanity) → Execute
    """

    def __init__(self):
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
            timeout=30.0,
            default_headers={
                "HTTP-Referer": "https://github.com/mt5-ai-bot",
                "X-Title": "MT5 AI Trading Panel",
            },
        )
        self.models = {
            "primary": AI_MODEL_PRIMARY,
            "validator": AI_MODEL_VALIDATOR,
            "fast": AI_MODEL_FAST,
            "fallback": AI_MODEL_FALLBACK,
        }

    async def decide(
        self,
        market_data: dict,
        strategy_signals: list[dict],
        news_formatted: str,
        risk_context: str,
        trade_history: str = "",
    ) -> dict[str, Any]:
        """
        Panel decision:
        1. ULTRA analyse tout et decide (BUY/SELL/WAIT + SL/TP)
        2. OWL verifie la decision d'ULTRA (peut veto)
        3. LAGUNA check rapide de coherence
        4. Si tout passe → Execute
        """

        # --- Phase 1: Primary (ULTRA) decides ---
        primary_decision = await self._ask_primary(
            market_data, strategy_signals, news_formatted, risk_context, trade_history
        )

        # Si ULTRA echoue ou retourne vide/parse error, utiliser le fallback
        if primary_decision.get("error") or (
            primary_decision.get("action") == "WAIT"
            and primary_decision.get("confidence", 0) == 0
            and "Parse error" in primary_decision.get("reasoning", "")
        ):
            logger.warning("AITrader: ULTRA indisponible, tentative fallback SUPER...")
            primary_decision = await self._ask_fallback(
                market_data, strategy_signals, news_formatted, risk_context
            )

        action = primary_decision.get("action", "WAIT")
        if action == "WAIT":
            logger.info(f"AI Panel: ULTRA says WAIT — {primary_decision.get('reasoning', '')[:80]}")
            return primary_decision

        if not AI_PANEL_ENABLED:
            logger.info(f"AI Panel: solo mode — {action} conf={primary_decision['confidence']}")
            return primary_decision

        # --- Phase 2: Validator (OWL) reviews ---
        veto_count = 0
        validator_ok = await self._ask_validator(
            primary_decision, market_data, news_formatted, risk_context
        )
        if not validator_ok:
            veto_count += 1
            logger.warning(f"AI Panel: OWL veto on {action}")

        # --- Phase 3: Fast check (LAGUNA) ---
        fast_ok = await self._ask_fast_check(
            primary_decision, market_data
        )
        if not fast_ok:
            veto_count += 1
            logger.warning(f"AI Panel: LAGUNA veto on {action}")

        # --- Decision finale ---
        if veto_count >= AI_VETO_THRESHOLD:
            logger.warning(
                f"AI Panel: {action} REJETE ({veto_count} vetos) — WAIT"
            )
            return {
                "action": "WAIT",
                "confidence": 0,
                "sl_price": None,
                "tp_price": None,
                "reasoning": f"Veto du panel ({veto_count} votes contre) — {primary_decision.get('reasoning', '')}",
            }

        logger.info(
            f"AI Panel: {action} CONFIRME conf={primary_decision['confidence']} "
            f"(vetos={veto_count})"
        )
        return primary_decision

    # ------------------------------------------------------------------
    # Phase 1: ULTRA 550B — Deep analysis
    # ------------------------------------------------------------------

    async def _ask_primary(
        self, market, signals, news, risk, history
    ) -> dict:
        prompt = self._build_prompt(market, signals, news, risk, history)

        try:
            response = await self.client.chat.completions.create(
                model=self.models["primary"],
                messages=[
                    {"role": "system", "content": self._system_prompt_primary()},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=600,
            )
        except Exception as e:
            logger.error(f"Primary (ULTRA) API error: {e}")
            return {"action": "WAIT", "confidence": 0, "error": str(e), "reasoning": "ULTRA indisponible"}

        content = response.choices[0].message.content if response.choices else ""
        if not content:
            logger.warning(f"AITrader: ULTRA rate limit — cooldown 60s")
            await asyncio.sleep(60)  # Attendre que le rate limit se reset
        else:
            logger.debug(f"AITrader: ULTRA response ({len(content)} chars): {content[:200]}")
        decision = self._parse_response(content)
        decision = self._validate_decision(decision, market)
        return decision

    # ------------------------------------------------------------------
    # Phase 2: OWL Alpha — Validate ULTRA's decision
    # ------------------------------------------------------------------

    async def _ask_validator(self, primary_decision: dict, market, news, risk) -> bool:
        """OWL verifie la decision d'ULTRA. Retourne True si OK, False si veto."""
        prompt = f"""Tu es un validateur de trading. Verifie cette decision:

DECISION A VALIDER:
Action: {primary_decision['action']}
SL: {primary_decision.get('sl_price', 'N/A')}
TP: {primary_decision.get('tp_price', 'N/A')}
Confiance: {primary_decision.get('confidence')}%
Raison: {primary_decision.get('reasoning', 'N/A')}

MARCHE:
Bid: {market.get('bid')} | EMA50: {market.get('ema50_m5')} | EMA200 M15: {market.get('ema200_m15')}
ATR: {market.get('atr')} | RSI: {market.get('rsi')} | Tendance: {market.get('trend_m15')}

RISK: {risk}

Reponds uniquement "OK" si la decision est coherente avec le marche et le risque, ou "VETO: raison" si tu trouves une erreur grave (SL du mauvais cote, TP/SL ratio absurde, trade contre la tendance, etc)."""

        try:
            response = await self.client.chat.completions.create(
                model=self.models["validator"],
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=100,
            )
            content = response.choices[0].message.content.strip() if response.choices else "VETO: pas de reponse"

            if content.upper().startswith("OK"):
                return True
            else:
                logger.info(f"AI Panel: OWL — {content}")
                return False

        except Exception as e:
            logger.warning(f"Validator (OWL) error: {e} — bypass")
            return True  # Fail-open: si OWL est down, faire confiance a ULTRA

    # ------------------------------------------------------------------
    # Phase 3: LAGUNA — Quick sanity check
    # ------------------------------------------------------------------

    async def _ask_fast_check(self, primary_decision: dict, market) -> bool:
        """LAGUNA check rapide: le prix et la tendance sont-ils coherents ?"""
        prompt = f"""Quick check:
Action: {primary_decision['action']}
Bid: {market.get('bid')} | EMA200 M15: {market.get('ema200_m15')}
RSI: {market.get('rsi')} | Tendance M15: {market.get('trend_m15')}

Reponds "OK" si l'action est coherente avec la tendance et les niveaux, ou "VETO" si l'action est clairement contre la tendance ou si le prix est a un niveau extreme."""

        try:
            response = await self.client.chat.completions.create(
                model=self.models["fast"],
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=50,
            )
            content = response.choices[0].message.content.strip() if response.choices else "VETO"
            return content.upper().startswith("OK")
        except Exception as e:
            logger.warning(f"Fast (LAGUNA) error: {e} — bypass")
            return True

    # ------------------------------------------------------------------
    # Fallback: Nemotron Super 120B (if ULTRA down)
    # ------------------------------------------------------------------

    async def _ask_fallback(self, market, signals, news, risk) -> dict:
        try:
            prompt = self._build_prompt(market, signals, news, risk)
            response = await self.client.chat.completions.create(
                model=self.models["fallback"],
                messages=[
                    {"role": "system", "content": self._system_prompt_primary()},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=600,
            )
            content = response.choices[0].message.content if response.choices else ""
            decision = self._parse_response(content)
            return self._validate_decision(decision, market)
        except Exception as e:
            logger.error(f"Fallback API error: {e}")
            return {"action": "WAIT", "confidence": 0, "error": str(e), "reasoning": "Tous les modeles indisponibles"}

    # ------------------------------------------------------------------
    # System prompts
    # ------------------------------------------------------------------

    def _system_prompt_primary(self) -> str:
        return f"""Tu es un trader XAUUSD expert. Mode STRATEGIE LIBRE.

Tu analyses: patterns de bougies, supports/resistances, divergences RSI, double tops/bottoms, drapeaux, triangles, order blocks, correlation DXY implicite, volume, volatilite, news.

Les strategies hardcodees (Breakout, EMA+RSI, Engulfing) sont des SUGGESTIONS. Tu peux les ignorer et proposer ton propre trade.

REGLES:
- Ratio TP/SL >= {AI_RISK_REWARD_MIN}
- SL entre {AI_SL_MIN_PIPS} et {AI_SL_MAX_PIPS} pips selon ATR
- JAMAIS contre la tendance EMA200 M15
- News USD majeure 30min → WAIT
- Setup incertain → WAIT (la qualite > la quantite)

Confiance:
- 90-100: Setup parfait (tout aligne)
- 70-89: Bon setup
- 60-69: Setup correct avec reserves
- <60: Ne pas executer

IMPERATIF: Reponds UNIQUEMENT avec le JSON ci-dessous. Pas de texte avant. Pas d'analyse. Le JSON doit etre le tout premier caractere de ta reponse:
{{"action":"BUY"|"SELL"|"WAIT","confidence":0-100,"sl_price":nombre,"tp_price":nombre,"reasoning":"10 mots max"}}"""

    # ------------------------------------------------------------------
    # Prompt builder
    # ------------------------------------------------------------------

    def _build_prompt(self, market, signals, news, risk, history="") -> str:
        lines = [
            f"[{SYMBOL} M5 — {datetime.now(timezone.utc).strftime('%H:%M UTC')}]",
            f"Bid:{market.get('bid')} Ask:{market.get('ask')} Spread:{market.get('spread')}",
            f"EMA50:{market.get('ema50_m5')} EMA200 M5:{market.get('ema200_m5')} EMA200 M15:{market.get('ema200_m15')}",
            f"RSI:{market.get('rsi')} ATR:{market.get('atr')}",
            f"Volume tick:{market.get('tick_volume','?')} DXY:{market.get('dxy','?')}",
            f"Tendance M15:{market.get('trend_m15')}",
        ]
        if history:
            lines.append(f"")
            lines.append(f"[DERNIERS TRADES]")
            lines.append(history)

        lines.append(f"")
        lines.append(f"[BOUGIES RECENTES — O/H/L/C/Dir]")
        lines.append(market.get('candles', '?'))

        lines.append(f"")
        lines.append(f"[STRATEGIES — suggestions]")
        for s in signals:
            d = s.get("direction", "NONE")
            lines.append(f"- {s['name']}: {d}" + (f" SL:{s.get('sl_price'):.2f} TP:{s.get('tp_price'):.2f}" if d != "NONE" else ""))

        lines.append(f"")
        lines.append(f"[NEWS]")
        lines.append(news)
        lines.append(f"")
        lines.append(f"[RISK]")
        lines.append(risk)

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Parsing & validation
    # ------------------------------------------------------------------

    def _parse_response(self, text: str) -> dict:
        if not text:
            logger.warning("AITrader: reponse vide du modele (rate limit?)")
            return {"action": "WAIT", "confidence": 0, "sl_price": None, "tp_price": None, "reasoning": "Reponse vide (rate limit?)"}

        # Pattern 1: markdown code block ```json ... ```
        match = re.search(r"```json\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Pattern 2: raw JSON looking for action field
        match = re.search(r'\{[^{}]*"action"[^{}]*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        # Pattern 3: find any JSON object in the text
        match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                if "action" in data:
                    return data
            except json.JSONDecodeError:
                pass

        # Pattern 4: extract action from plain text (BUY/SELL/WAIT)
        # Le modele ne produit pas de JSON, mais on peut extraire sa direction
        text_upper = text.upper()
        if "BUY" in text_upper and "SELL" not in text_upper:
            logger.info(f"AITrader: BUY detecte dans le texte brut")
            return {"action": "BUY", "confidence": 65, "sl_price": None, "tp_price": None, "reasoning": f"Texte brut: {text[:80]}"}
        if "SELL" in text_upper and "BUY" not in text_upper:
            logger.info(f"AITrader: SELL detecte dans le texte brut")
            return {"action": "SELL", "confidence": 65, "sl_price": None, "tp_price": None, "reasoning": f"Texte brut: {text[:80]}"}

        logger.warning(f"AITrader: parse fail — {text[:300]}")
        return {"action": "WAIT", "confidence": 0, "sl_price": None, "tp_price": None, "reasoning": "Parse error"}

    def _validate_decision(self, decision: dict, market: dict) -> dict:
        action = decision.get("action", "WAIT")
        if action not in ("BUY", "SELL"):
            return {"action": "WAIT", "confidence": 0, "sl_price": None, "tp_price": None, "reasoning": decision.get("reasoning", "")}
        if action == "WAIT":
            return decision

        sl = decision.get("sl_price")
        tp = decision.get("tp_price")
        bid = float(str(market.get("bid", "0")).replace(",", "."))
        atr = float(str(market.get("atr", "0")).replace(",", "."))

        # Si SL/TP manquants, les calculer depuis l'ATR
        if (not sl or not tp) and atr > 0 and bid > 0:
            sl_mult = 1.5  # SL = 1.5x ATR
            tp_mult = 3.0  # TP = 3.0x ATR (ratio 1:2)
            if action == "BUY":
                sl = bid - (atr * sl_mult)
                tp = bid + (atr * tp_mult)
            else:
                sl = bid + (atr * sl_mult)
                tp = bid - (atr * tp_mult)
            logger.info(
                f"AITrader: SL/TP auto (ATR) — sl={sl:.2f} tp={tp:.2f} atr={atr:.3f}"
            )

        if not sl or not tp or bid == 0:
            return {"action": "WAIT", "confidence": 0, "sl_price": None, "tp_price": None, "reasoning": "SL/TP manquant"}

        if action == "BUY" and sl >= bid:
            return {"action": "WAIT", "confidence": 0, "sl_price": None, "tp_price": None, "reasoning": f"SL({sl}) >= prix({bid})"}
        if action == "SELL" and sl <= bid:
            return {"action": "WAIT", "confidence": 0, "sl_price": None, "tp_price": None, "reasoning": f"SL({sl}) <= prix({bid})"}

        risk = bid - sl if action == "BUY" else sl - bid
        reward = tp - bid if action == "BUY" else bid - tp
        if risk <= 0 or reward <= 0 or reward / risk < AI_RISK_REWARD_MIN:
            return {"action": "WAIT", "confidence": 0, "sl_price": None, "tp_price": None, "reasoning": f"Ratio R/R bas ({reward/risk:.1f})"}

        return decision
