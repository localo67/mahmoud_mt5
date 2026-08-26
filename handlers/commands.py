"""
Handlers pour les commandes Telegram (/start, /help, /solde, etc.).
Tous les messages sont en francais avec emojis.
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# /start - Menu principal avec boutons inline
# ------------------------------------------------------------------


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Message de bienvenue avec clavier inline d'actions rapides."""
    keyboard = [
        [
            InlineKeyboardButton(" Solde", callback_data="solde"),
            InlineKeyboardButton(" Positions", callback_data="positions"),
        ],
        [
            InlineKeyboardButton(" Analyse EURUSD", callback_data="analyse_EURUSD"),
            InlineKeyboardButton(" Analyse XAUUSD", callback_data="analyse_XAUUSD"),
        ],
        [
            InlineKeyboardButton(" Aide ", callback_data="aide"),
        ],
    ]

    await update.message.reply_text(
        " Bonjour ! Je suis votre **assistant de trading IA** connecte a MetaTrader 5.\n\n"
        "Je peux :\n"
        " Consulter votre compte et vos positions (lecture seule)\n"
        " Analyser les marches\n"
        " Afficher l'etat du bot et des bloqueurs\n\n"
        " Telegram ne peut pas passer d'ordre ni armer le trading.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN,
    )


# ------------------------------------------------------------------
# /help - Aide detaillee
# ------------------------------------------------------------------

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche l'aide complete."""

    help_text = (
        " *Aide - Bot de Trading MT5 + IA*\n\n"
        "*Commandes disponibles :*\n"
        "/start - Menu principal avec actions rapides\n"
        "/help - Cette aide\n"
        "/solde - Consulter votre solde et capital\n"
        "/positions - Lister vos positions ouvertes\n"
        "/analyse \\<symbole\\> - Analyse technique rapide\n"
        "/auto on|off - Activer/desactiver l'automation\n\n"
        "*Exemples en langage naturel :*\n"
        " _\"Achete 0.1 lot EURUSD avec SL a 1.0500\"_\n"
        " _\"Vends 0.5 XAUUSD\"_\n"
        " _\"Quel est mon solde ?\"_\n"
        " _\"Montre mes positions\"_\n"
        " _\"Analyse GBPUSD\"_\n"
        " _\"Ferme le ticket 12345678\"_\n"
        " _\"Ferme toutes mes positions\"_\n"
        " _\"Modifie le SL du ticket 12345678 a 1.0850\"_"
    )

    await update.message.reply_text(
        help_text,
        parse_mode=ParseMode.MARKDOWN,
    )


# ------------------------------------------------------------------
# /solde - Information du compte
# ------------------------------------------------------------------

async def solde_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le solde et les infos du compte (court-circuite l'IA)."""
    mt5 = context.bot_data.get("mt5_client")
    if mt5 is None:
        await update.message.reply_text(" MT5 non initialise.")
        return

    try:
        if not await mt5.check_connection():
            await update.message.reply_text(" Impossible de se connecter a MT5.")
            return

        info = await mt5.get_account_info()
        profit = info["equity"] - info["balance"]
        pnl_emoji = "+" if profit >= 0 else "-"

        text = (
            f" *Etat du compte*\n\n"
            f" Compte : {info['name']} (#{info['login']})\n"
            f" Serveur : {info['server']}\n\n"
            f" Solde : *{info['balance']:,.2f}* {info['currency']}\n"
            f" Capital : *{info['equity']:,.2f}* {info['currency']}\n"
            f" P&L flottant : {profit:+,.2f} {info['currency']} {pnl_emoji}\n"
            f" Marge libre : {info['free_margin']:,.2f} {info['currency']}\n"
            f" Levier : 1:{info['leverage']}"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        logger.exception("Erreur /solde")
        await update.message.reply_text(f" Erreur : {str(e)}")


# ------------------------------------------------------------------
# /positions - Positions ouvertes
# ------------------------------------------------------------------

async def positions_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Liste les positions ouvertes (court-circuite l'IA)."""
    mt5 = context.bot_data.get("mt5_client")
    if mt5 is None:
        await update.message.reply_text(" MT5 non initialise.")
        return

    try:
        if not await mt5.check_connection():
            await update.message.reply_text(" Impossible de se connecter a MT5.")
            return

        positions = await mt5.get_positions()

        if not positions:
            await update.message.reply_text(" Aucune position ouverte. ")
            return

        total_pnl = sum(p["profit"] for p in positions)
        pnl_emoji = " " if total_pnl >= 0 else " "

        lines = [f" *Positions ouvertes ({len(positions)})* \n"]
        for p in positions:
            dir_emoji = "LONG" if p["type"] == "BUY" else "SHORT"
            sl_s = f"{p['sl']:.5f}" if p["sl"] and p["sl"] > 0 else "Aucun"
            tp_s = f"{p['tp']:.5f}" if p["tp"] and p["tp"] > 0 else "Aucun"
            pnl_s = f"{p['profit']:+,.2f}"

            lines.append(
                f"{dir_emoji} *Ticket {p['ticket']}* - {p['symbol']} {p['type']}\n"
                f"   Vol: {p['volume']} | Ouvert: {p['price_open']:.5f} | Actuel: {p['price_current']:.5f}\n"
                f"   SL: {sl_s} | TP: {tp_s}\n"
                f"   P&L: {pnl_s} | Swap: {p['swap']:+,.2f}"
            )

        lines.append(f"\n P&L total : *{total_pnl:+,.2f}* {pnl_emoji}")

        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        logger.exception("Erreur /positions")
        await update.message.reply_text(f" Erreur : {str(e)}")


# ------------------------------------------------------------------
# /analyse <symbole> - Analyse technique rapide
# ------------------------------------------------------------------

async def analyse_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Analyse technique rapide d'un symbole."""
    mt5 = context.bot_data.get("mt5_client")
    dispatcher = context.bot_data.get("dispatcher")

    if mt5 is None or dispatcher is None:
        await update.message.reply_text(" Services non initialises.")
        return

    # Extraire le symbole des arguments
    symbol = "EURUSD"
    if context.args:
        symbol = context.args[0].upper()

    try:
        response = await dispatcher.execute({
            "function": "get_technical_analysis",
            "arguments": {"symbol": symbol},
        })
        await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.exception("Erreur /analyse")
        await update.message.reply_text(f" Erreur : {str(e)}")


# ------------------------------------------------------------------
# /auto on|off - Controle de l'automation
# ------------------------------------------------------------------

async def auto_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lecture seule: l'automation ne peut plus etre armee depuis Telegram."""
    auto_engine = context.bot_data.get("auto_engine")

    if auto_engine is None:
        await update.message.reply_text(" Moteur d'automation non initialise.")
        return

    status = "activee" if getattr(auto_engine, "enabled", False) else "desactivee"
    await update.message.reply_text(
        f"Automation: {status}. Telegram est en lecture seule: "
        "/auto ne peut plus activer, desarmer ni armer le trading."
    )


# ------------------------------------------------------------------
# /status - Etat du risk manager
# ------------------------------------------------------------------

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche l'etat du risk manager et la distribution des bloqueurs."""
    auto_engine = context.bot_data.get("auto_engine")

    if auto_engine is None:
        await update.message.reply_text("Moteur d'automation non initialise.")
        return

    status = auto_engine.get_risk_status()
    report = auto_engine.get_blocker_report()
    distribution = report.get("distribution") or {}
    dist_lines = [
        f"  {code}: {count}"
        for code, count in sorted(distribution.items(), key=lambda item: (-item[1], item[0]))
    ]
    blockers_text = "\n".join(dist_lines) if dist_lines else "  aucun"
    last_blockers = ", ".join(report.get("last_blockers") or []) or "-"
    text = (
        f"{status}\n\n"
        f"Mode: {report.get('mode', 'unknown')}\n"
        f"Bougies evaluees: {report.get('evaluated_candles', 0)}\n"
        f"Dernier resultat: {report.get('last_outcome') or '-'}\n"
        f"Derniers bloqueurs: {last_blockers}\n"
        f"Distribution:\n{blockers_text}"
    )
    await update.message.reply_text(text)


# ------------------------------------------------------------------
# /reset - Reinitialiser le risk manager
# ------------------------------------------------------------------

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lecture seule: refuse de lever le kill switch ou de resetter le risque."""
    auto_engine = context.bot_data.get("auto_engine")

    if auto_engine is None:
        await update.message.reply_text("Moteur d'automation non initialise.")
        return

    status = auto_engine.reset_risk()
    await update.message.reply_text(
        f"Reset refuse. Telegram est en lecture seule.\n\n{status}"
    )
