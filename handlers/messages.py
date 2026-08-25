"""
Handlers pour les messages texte libres (langage naturel)
et les callbacks des boutons inline Telegram.
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Messages texte libres -> AI Engine -> Dispatcher
# ------------------------------------------------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Traite un message texte libre en francais.
    Passe par l'IA pour comprendre l'intention, puis execute l'action.
    """
    user_text = update.message.text
    logger.info(f"Message recu : {user_text[:100]}")

    ai_engine = context.bot_data.get("ai_engine")
    dispatcher = context.bot_data.get("dispatcher")

    if ai_engine is None or dispatcher is None:
        await update.message.reply_text(
            "Services non initialises. Verifiez la configuration."
        )
        return

    # Indicateur "en train d'ecrire..." (non critique)
    try:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action="typing",
        )
    except Exception:
        pass

    # Envoyer a l'IA pour analyse
    result = await ai_engine.process_message(user_text)

    if result["intent"] == "trade_command":
        # Executer l'action de trading
        response = await dispatcher.execute(result["action"])
        await update.message.reply_text(response)

        # Proposer des actions rapides apres execution
        keyboard = [
            [
                InlineKeyboardButton("Solde", callback_data="solde"),
                InlineKeyboardButton("Positions", callback_data="positions"),
            ],
            [
                InlineKeyboardButton("Analyse EURUSD", callback_data="analyse_EURUSD"),
            ],
        ]
        await update.message.reply_text(
            "Actions rapides :",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif result["intent"] == "chat":
        # Reponse conversationnelle
        await update.message.reply_text(
            result.get("response", "D'accord !")
        )

    elif result["intent"] == "error":
        # Erreur OpenAI
        await update.message.reply_text(
            result.get("response", "Une erreur est survenue.")
        )


# ------------------------------------------------------------------
# Callbacks des boutons inline
# ------------------------------------------------------------------

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Gere les clics sur les boutons inline.
    callback_data possibles : solde, positions, analyse_X, auto_on, auto_off, aide
    """
    query = update.callback_query
    await query.answer()

    mt5 = context.bot_data.get("mt5_client")
    dispatcher = context.bot_data.get("dispatcher")
    auto_engine = context.bot_data.get("auto_engine")
    data = query.data

    logger.info(f"Callback : {data}")

    # --- Solde ---
    if data == "solde":
        if mt5 is None:
            await query.edit_message_text("MT5 non initialise.")
            return
        try:
            if not await mt5.check_connection():
                await query.edit_message_text("Connexion MT5 perdue.")
                return
            info = await mt5.get_account_info()
            profit = info["equity"] - info["balance"]
            pnl_emoji = "+" if profit >= 0 else "-"
            text = (
                f"Solde du compte\n\n"
                f"Solde : {info['balance']:,.2f} {info['currency']}\n"
                f"Capital : {info['equity']:,.2f} {info['currency']}\n"
                f"P&L flottant : {profit:+,.2f} {info['currency']} [{pnl_emoji}]\n"
                f"Marge libre : {info['free_margin']:,.2f} {info['currency']}"
            )
            await query.edit_message_text(text)
        except Exception as e:
            await query.edit_message_text(f"Erreur : {str(e)}")

    # --- Positions ---
    elif data == "positions":
        if mt5 is None:
            await query.edit_message_text("MT5 non initialise.")
            return
        try:
            if not await mt5.check_connection():
                await query.edit_message_text("Connexion MT5 perdue.")
                return
            positions = await mt5.get_positions()
            if not positions:
                await query.edit_message_text("Aucune position ouverte.")
                return
            total_pnl = sum(p["profit"] for p in positions)
            pnl_emoji = "+" if total_pnl >= 0 else "-"
            lines = [f"Positions ({len(positions)}) :\n"]
            for p in positions:
                dir_emoji = "LONG" if p["type"] == "BUY" else "SHORT"
                sl_s = f"{p['sl']:.5f}" if p["sl"] and p["sl"] > 0 else "-"
                tp_s = f"{p['tp']:.5f}" if p["tp"] and p["tp"] > 0 else "-"
                lines.append(
                    f"[{dir_emoji}] Ticket #{p['ticket']} {p['symbol']}\n"
                    f"   Vol: {p['volume']} | P&L: {p['profit']:+,.2f} | SL: {sl_s} | TP: {tp_s}"
                )
            lines.append(f"\nTotal P&L : {total_pnl:+,.2f} [{pnl_emoji}]")
            await query.edit_message_text("\n".join(lines))
        except Exception as e:
            await query.edit_message_text(f"Erreur : {str(e)}")

    # --- Analyse ---
    elif data.startswith("analyse_"):
        symbol = data.replace("analyse_", "")
        if dispatcher is None:
            await query.edit_message_text("Dispatcher non initialise.")
            return
        try:
            response = await dispatcher.execute({
                "function": "get_technical_analysis",
                "arguments": {"symbol": symbol},
            })
            await query.edit_message_text(response)
        except Exception as e:
            await query.edit_message_text(f"Erreur : {str(e)}")

    # --- Automation ON/OFF ---
    elif data == "auto_on":
        if auto_engine is None:
            await query.edit_message_text("Moteur d'automation non initialise.")
            return
        await auto_engine.set_enabled(True)
        await query.edit_message_text(
            "Automation activee !\n"
            "Vous recevrez des alertes Telegram a chaque signal de trading."
        )

    elif data == "auto_off":
        if auto_engine is None:
            await query.edit_message_text("Moteur d'automation non initialise.")
            return
        await auto_engine.set_enabled(False)
        await query.edit_message_text(
            "Automation desactivee.\n"
            "Les strategies sont en pause."
        )

    # --- Aide ---
    elif data == "aide":
        await query.edit_message_text(
            "Aide rapide\n\n"
            "Envoyez-moi un message en francais ! Exemples :\n\n"
            '"Achete 0.1 lot EURUSD"\n'
            '"Vends 0.5 XAUUSD avec SL a 2500"\n'
            '"Quel est mon solde ?"\n'
            '"Montre mes positions"\n'
            '"Analyse GBPUSD"\n'
            '"Ferme le ticket 12345678"\n'
            '"Ferme toutes mes positions"'
        )

    else:
        logger.warning(f"Callback inconnu : {data}")
        await query.edit_message_text(f"Action inconnue : {data}")
