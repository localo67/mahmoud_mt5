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
            InlineKeyboardButton(" Automation ON ", callback_data="auto_on"),
            InlineKeyboardButton(" Automation OFF ", callback_data="auto_off"),
        ],
        [
            InlineKeyboardButton(" Aide ", callback_data="aide"),
        ],
    ]

    await update.message.reply_text(
        " Bonjour ! Je suis votre **assistant de trading IA** connecte a MetaTrader 5.\n\n"
        "Je peux :\n"
        " Executer des ordres en langage naturel\n"
        " Consulter votre compte et vos positions\n"
        " Analyser les marches (MA20, MA50, tendance)\n"
        " Automatiser des strategies (MA crossover + RSI)\n\n"
        " Utilisez les boutons ci-dessous ou envoyez-moi un message en francais !",
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
    """Active ou desactive l'automation des strategies."""
    auto_engine = context.bot_data.get("auto_engine")

    if auto_engine is None:
        await update.message.reply_text(" Moteur d'automation non initialise.")
        return

    if not context.args:
        status = "activee " if auto_engine.enabled else "desactivee "
        await update.message.reply_text(
            f" Automation : {status}\n"
            f"Usage : /auto on ou /auto off"
        )
        return

    cmd = context.args[0].lower()
    if cmd == "on":
        await auto_engine.set_enabled(True)
        await update.message.reply_text(
            " Automation activee ! \n"
            "Les strategies MA Crossover et RSI tournent en arriere-plan.\n"
            "Vous recevrez une alerte Telegram a chaque signal."
        )
    elif cmd == "off":
        await auto_engine.set_enabled(False)
        await update.message.reply_text(
            " Automation desactivee . \n"
            "Les strategies sont en pause."
        )
    else:
        await update.message.reply_text(
            " Usage : /auto on ou /auto off"
        )


# ------------------------------------------------------------------
# /status - Etat du risk manager
# ------------------------------------------------------------------

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche l'etat du risk manager."""
    auto_engine = context.bot_data.get("auto_engine")

    if auto_engine is None:
        await update.message.reply_text("Moteur d'automation non initialise.")
        return

    status = auto_engine.get_risk_status()
    await update.message.reply_text(status)


# ------------------------------------------------------------------
# /reset - Reinitialiser le risk manager
# ------------------------------------------------------------------

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reinitialise le risk manager (pertes, compteur, blocage)."""
    auto_engine = context.bot_data.get("auto_engine")

    if auto_engine is None:
        await update.message.reply_text("Moteur d'automation non initialise.")
        return

    status = auto_engine.reset_risk()
    await update.message.reply_text(
        f"Risk manager reinitialise !\n\n{status}"
    )
