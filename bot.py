#!/usr/bin/env python3
"""
Bot de trading MT5 + IA + Telegram.
Point d'entree principal : assemble tous les composants et demarre l'application.

Usage :
    python bot.py --headless --arm-demo --pack scalp_eurusd_m1
    (TRADING_MODE=demo dans .env, compte MT5 demo, Windows)

Arret : Ctrl+C (arret propre avec deconnexion MT5)
"""

import argparse
import asyncio
import logging
import os
import signal
from pathlib import Path

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

from config import TELEGRAM_TOKEN, AUTHORIZED_CHAT_ID, TRADING_MODE, validate_config
from mt5_client import MT5Client
from ai_engine import AIEngine
from tools.dispatcher import Dispatcher
from handlers.commands import (
    start,
    help_command,
    solde_command,
    positions_command,
    analyse_command,
    auto_command,
    status_command,
    reset_command,
)
from handlers.messages import handle_message, handle_callback
from automation import AutomationEngine

# ------------------------------------------------------------------
# Configuration du logging
# ------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)
# Reduire le bruit des librairies tierces
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram.ext.Application").setLevel(logging.WARNING)

logger = logging.getLogger("bot")


def configure_file_logging() -> None:
    log_file = os.getenv("LOG_FILE")
    if not log_file:
        return
    path = Path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logging.getLogger().addHandler(handler)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Bot trading MT5 demo")
    parser.add_argument(
        "--arm-demo",
        action="store_true",
        help="Autorise les ordres sur un compte demo (argent fictif). Pas persiste.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Sans Telegram : uniquement le moteur de trading.",
    )
    parser.add_argument(
        "--pack",
        default=None,
        help="Id du pack (ex: scalp_eurusd_m1). Defaut: STRATEGY_PACK ou session_breakout_xauusd.",
    )
    return parser.parse_args(argv)


def arm_demo_if_requested(mt5_client, arm_demo: bool) -> bool:
    """Arme les ordres demo uniquement si demande explicitement au lancement."""
    if not arm_demo:
        if getattr(mt5_client, "trading_mode", TRADING_MODE) == "demo":
            logger.warning(
                "TRADING_MODE=demo sans --arm-demo: le bot observe, aucun ordre envoye."
            )
        return True
    if getattr(mt5_client, "trading_mode", TRADING_MODE) != "demo":
        logger.error("--arm-demo n'est autorise qu'avec TRADING_MODE=demo")
        return False
    mt5_client.arm_trading()
    logger.warning("DEMO ARME: le bot peut envoyer des ordres sur le compte fictif.")
    return True


async def initialize_mt5_for_runtime(mt5_client, trading_mode: str):
    """Initialise MT5 uniquement pour les modes qui en dependent."""
    if trading_mode == "off":
        return None
    return await mt5_client.initialize()

# ------------------------------------------------------------------
# Middleware de securite
# ------------------------------------------------------------------


def check_authorization(update: Update) -> bool:
    """
    Verifie que l'utilisateur est autorise a utiliser le bot.
    Compare chat_id et user_id avec AUTHORIZED_CHAT_ID.

    Returns:
        True si autorise, False sinon.
    """
    # Mode dev : si AUTHORIZED_CHAT_ID = 0, tout le monde est autorise
    if AUTHORIZED_CHAT_ID == 0:
        return True

    user_id = update.effective_user.id if update.effective_user else None
    chat_id = update.effective_chat.id if update.effective_chat else None

    if user_id == AUTHORIZED_CHAT_ID or chat_id == AUTHORIZED_CHAT_ID:
        return True

    logger.warning(f"  ACCES REFUSE : user_id={user_id}, chat_id={chat_id}")
    return False


def authorized(handler_func):
    """
    Decorateur qui verifie l'autorisation avant d'executer le handler.
    Bloque silencieusement les utilisateurs non autorises.
    """
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not check_authorization(update):
            # Repondre uniquement si c'est un message direct
            if update.message:
                await update.message.reply_text(
                    " Acces refuse. Vous n'etes pas autorise a utiliser ce bot.\n"
                    "Contactez l'administrateur pour obtenir l'acces."
                )
            elif update.callback_query:
                await update.callback_query.answer(
                    " Acces refuse.", show_alert=True
                )
            return
        return await handler_func(update, context)
    return wrapper


# ------------------------------------------------------------------
# Gestionnaire d'erreurs global
# ------------------------------------------------------------------

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Capture toutes les exceptions non gerees des handlers."""
    logger.error(
        f"Exception dans un handler : {context.error}",
        exc_info=context.error,
    )

    # Informer l'utilisateur si possible
    if update and hasattr(update, "effective_chat"):
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=(
                    " Une erreur interne est survenue.\n"
                    "Verifiez les logs pour plus de details."
                ),
            )
        except Exception:
            pass


# ------------------------------------------------------------------
# Point d'entree principal
# ------------------------------------------------------------------

async def run_headless(mt5, pack_id: str | None) -> None:
    auto_engine = AutomationEngine(None, mt5, pack_id=pack_id)
    logger.info("Mode headless pack=%s (Ctrl+C pour arreter)", auto_engine.pack.id)
    stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()

    def signal_handler():
        logger.info("Signal d'arret recu...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            pass

    automation_task = asyncio.create_task(auto_engine.run(), name="automation_engine")
    try:
        await stop_event.wait()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt recu...")
    automation_task.cancel()
    try:
        await automation_task
    except asyncio.CancelledError:
        pass


async def main(argv=None) -> None:
    """Fonction principale asynchrone."""
    configure_file_logging()
    args = parse_args(argv)

    logger.info("=" * 50)
    logger.info("  MT5 Demo Bot - Demarrage")
    logger.info("=" * 50)

    if not validate_config(headless=args.headless):
        logger.error("Configuration invalide. Verifiez votre fichier .env")
        return

    logger.info(f"Chat autorise : {AUTHORIZED_CHAT_ID}")

    # 2. Initialiser le client MT5
    mt5 = MT5Client()
    if not arm_demo_if_requested(mt5, args.arm_demo):
        return
    init_ok = await initialize_mt5_for_runtime(mt5, TRADING_MODE)

    if init_ok is None:
        logger.info(
            "TRADING_MODE=off : runtime non-MT5, initialisation MT5 ignoree."
        )
    elif not init_ok:
        logger.error(
            " ECHEC de connexion a MetaTrader 5.\n"
            "   - Le terminal MT5 est-il ouvert ?\n"
            "   - Les identifiants dans .env sont-ils corrects ?\n"
            "   - Le trading algorithmique est-il active ?\n"
            "Le bot demarre sans MT5 (commandes IA et Telegram uniquement)."
        )
        # On continue quand meme : l'utilisateur peut interagir avec l'IA

    if args.headless:
        if not init_ok:
            logger.error("Mode headless: connexion MT5 requise (TRADING_MODE=demo).")
            return
        try:
            await run_headless(mt5, args.pack)
        finally:
            if mt5.is_connected:
                await mt5.shutdown()
                logger.info("MT5 deconnecte.")
            MT5Client.shutdown_shared_executor()
            logger.info("Bot arrete proprement.")
        return

    # 3. Initialiser l'IA et le dispatcher
    ai = AIEngine()
    dispatcher = Dispatcher(mt5)
    logger.info(f"IA initialisee : modele = {ai.model}")

    # 4. Construire l'application Telegram
    application = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .connect_timeout(15)
        .read_timeout(30)
        .write_timeout(15)
        .pool_timeout(5)
        .build()
    )

    # 5. Injection de dependances dans bot_data
    application.bot_data["mt5_client"] = mt5
    application.bot_data["ai_engine"] = ai
    application.bot_data["dispatcher"] = dispatcher

    # 6. Enregistrer les handlers (avec decorateur @authorized)
    application.add_handler(CommandHandler("start", authorized(start)))
    application.add_handler(CommandHandler("help", authorized(help_command)))
    application.add_handler(CommandHandler("solde", authorized(solde_command)))
    application.add_handler(CommandHandler("positions", authorized(positions_command)))
    application.add_handler(CommandHandler("analyse", authorized(analyse_command)))
    application.add_handler(CommandHandler("auto", authorized(auto_command)))
    application.add_handler(CommandHandler("status", authorized(status_command)))
    application.add_handler(CommandHandler("reset", authorized(reset_command)))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, authorized(handle_message))
    )
    application.add_handler(CallbackQueryHandler(authorized(handle_callback)))
    application.add_error_handler(error_handler)

    # 7. Initialiser le moteur d'automation
    auto_engine = AutomationEngine(application, mt5, pack_id=args.pack)
    application.bot_data["auto_engine"] = auto_engine

    # 8. Demarrer l'application
    logger.info("Demarrage du bot Telegram...")

    async with application:
        await application.start()
        await application.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
        )

        logger.info(" Bot demarre et en ecoute ! (Ctrl+C pour arreter)")

        # Lancer l'automation en tache de fond
        automation_task = asyncio.create_task(
            auto_engine.run(),
            name="automation_engine",
        )

        # Gestion de l'arret avec signal
        stop_event = asyncio.Event()

        def signal_handler():
            logger.info("Signal d'arret recu...")
            stop_event.set()

        # Enregistrer les handlers de signal
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, signal_handler)
            except NotImplementedError:
                # Windows ne supporte pas add_signal_handler
                pass

        # Attendre l'arret
        try:
            await stop_event.wait()
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt recu...")

        # Nettoyage
        logger.info("Arret du bot...")

        # Arreter l'automation
        automation_task.cancel()
        try:
            await automation_task
        except asyncio.CancelledError:
            pass

        # Arreter le polling Telegram
        await application.updater.stop()
        await application.stop()

    # 9. Deconnexion MT5
    if mt5.is_connected:
        await mt5.shutdown()
        logger.info("MT5 deconnecte.")
    MT5Client.shutdown_shared_executor()

    logger.info("Bot arrete proprement. A bientot ! ")


# ------------------------------------------------------------------
# Lancement
# ------------------------------------------------------------------

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot arrete par l'utilisateur.")
