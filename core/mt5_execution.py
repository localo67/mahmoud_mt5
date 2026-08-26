"""Adapter demo MT5: check, send, lectures brutes. Aucune decision metier."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from core.filling import select_filling
from core.types import OrderIntent


class MT5DemoAdapter:
    backend = "mt5"
    simulated = False

    def __init__(self, mt5, spec=None):
        self.mt5 = mt5
        self.spec = spec

    def _filling(self, order: OrderIntent) -> int:
        api = getattr(self.mt5, "_mt5", None) or self.mt5
        if order.filling_mode is not None:
            return int(order.filling_mode)
        if self.spec is not None:
            return select_filling(self.spec.filling_mode, api)
        return getattr(api, "ORDER_FILLING_IOC", 1)

    async def check(self, order: OrderIntent) -> dict:
        filling = self._filling(order)
        comment = f"id:{order.decision_id}"
        result = await self.mt5.check_order(
            order.symbol,
            order.side,
            order.volume,
            sl=order.sl,
            tp=order.tp,
            filling=filling,
            comment=comment,
        )
        result = dict(result)
        result["backend"] = self.backend
        result["simulated"] = False
        return result

    async def send(self, order: OrderIntent) -> dict:
        filling = self._filling(order)
        comment = f"id:{order.decision_id}"
        result = await self.mt5.open_order(
            symbol=order.symbol,
            order_type=order.side,
            volume=order.volume,
            sl=order.sl,
            tp=order.tp,
            comment=comment,
            filling=filling,
        )
        result = dict(result)
        result["backend"] = self.backend
        result["simulated"] = False
        return result

    async def orders(self, symbol: str) -> list[dict]:
        getter = getattr(self.mt5, "get_orders", None)
        if getter is None:
            return []
        return await getter(symbol=symbol)

    async def history_orders(self, symbol: str) -> list[dict]:
        getter = getattr(self.mt5, "get_history_orders", None)
        if getter is None:
            return []
        now = datetime.now(timezone.utc)
        return await getter(now - timedelta(days=2), now, symbol=symbol)

    async def history_deals(self, symbol: str) -> list[dict]:
        getter = getattr(self.mt5, "get_history_deals", None)
        if getter is None:
            api = getattr(self.mt5, "_mt5", None)
            if api is None or not hasattr(api, "history_deals_get"):
                return []
            raw = api.history_deals_get()
            return [_deal(item) for item in raw or []]
        now = datetime.now(timezone.utc)
        return await getter(now - timedelta(days=2), now, symbol=symbol)

    async def positions(self, symbol: Optional[str] = None) -> list[dict]:
        return await self.mt5.get_positions(symbol=symbol)

    async def close(self, ticket: int) -> dict:
        return await self.mt5.close_position(ticket)

    async def modify(self, ticket: int, sl=None, tp=None) -> dict:
        return await self.mt5.modify_position(ticket=ticket, sl=sl, tp=tp)


def _deal(item) -> dict:
    return {
        "ticket": getattr(item, "ticket", None),
        "order": getattr(item, "order", None),
        "position_id": getattr(item, "position_id", None),
        "symbol": getattr(item, "symbol", None),
        "volume": getattr(item, "volume", 0.0),
        "price": getattr(item, "price", 0.0),
        "profit": getattr(item, "profit", 0.0),
        "magic": getattr(item, "magic", 0),
        "comment": getattr(item, "comment", ""),
        "entry": getattr(item, "entry", 0),
    }
