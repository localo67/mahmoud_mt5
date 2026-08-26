"""Selection du filling MT5 a partir du bitmask de specifications."""

from __future__ import annotations

SYMBOL_FILLING_FOK = 1
SYMBOL_FILLING_IOC = 2


def select_filling(filling_mode: int, api) -> int:
    """Choisit IOC, FOK ou RETURN selon le bitmask SYMBOL_FILLING_* du symbole."""
    ioc = getattr(api, "ORDER_FILLING_IOC", 1)
    fok = getattr(api, "ORDER_FILLING_FOK", 0)
    ret = getattr(api, "ORDER_FILLING_RETURN", 2)
    mask = int(filling_mode or 0)
    if mask & SYMBOL_FILLING_IOC:
        return ioc
    if mask & SYMBOL_FILLING_FOK:
        return fok
    return ret


def filling_name(value: int, api) -> str:
    if value == getattr(api, "ORDER_FILLING_IOC", 1):
        return "IOC"
    if value == getattr(api, "ORDER_FILLING_FOK", 0):
        return "FOK"
    if value == getattr(api, "ORDER_FILLING_RETURN", 2):
        return "RETURN"
    return str(value)
