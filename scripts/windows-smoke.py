#!/usr/bin/env python3
"""Smoke test Windows natif: off, shadow sans send, demo desarme.

Usage (PowerShell, venv active, terminal MT5 ouvert):

    $env:TRADING_MODE="off"; python scripts/windows-smoke.py
    $env:TRADING_MODE="shadow"; python scripts/windows-smoke.py
    $env:TRADING_MODE="demo"; python scripts/windows-smoke.py

L'envoi demo arme n'est pas execute ici. Il reste une validation manuelle
separee sur compte demo.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import TRADING_MODE  # noqa: E402
from mt5_client import MT5Client  # noqa: E402


async def main() -> int:
    mode = TRADING_MODE
    print(f"TRADING_MODE={mode}")
    if mode == "live":
        print("NO-GO: live reconnu mais non implemente.")
        return 2
    if mode == "off":
        print("OK: mode off, aucune connexion MT5 requise.")
        return 0

    client = MT5Client(trading_mode=mode)
    connected = await client.initialize()
    if not connected:
        print("NO-GO: connexion MT5 impossible.")
        return 1
    print(f"armed={client.is_trading_armed}")
    if mode == "shadow":
        if client.is_trading_armed:
            print("NO-GO: shadow ne doit pas etre arme.")
            return 1
        print("OK: shadow connecte, order_send reste refuse (client desarme, mode lecture).")
        return 0
    if mode == "demo":
        if client.is_trading_armed:
            print("NO-GO: ce smoke test refuse un client deja arme.")
            return 1
        print("OK: demo connecte et desarme. Pas d'order_send dans ce script.")
        print("Validation manuelle separee: arm_trading() uniquement sur compte demo.")
        return 0
    print(f"NO-GO: mode inattendu {mode}")
    return 2


if __name__ == "__main__":
    os.chdir(ROOT)
    raise SystemExit(asyncio.run(main()))
