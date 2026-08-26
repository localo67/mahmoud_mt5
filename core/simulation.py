"""Adapter shadow: order_check reel, fill BBO simule, jamais order_send."""

from __future__ import annotations

from typing import Optional

from core.types import OrderIntent


class ShadowAdapter:
    backend = "shadow"
    simulated = True

    def __init__(self, mt5, magic: int = 20240601):
        self.mt5 = mt5
        self.magic = int(magic)
        self.virtual_positions: list[dict] = []
        self.virtual_deals: list[dict] = []
        self._next_id = 10_000

    async def check(self, order: OrderIntent) -> dict:
        comment = f"id:{order.decision_id}"
        result = await self.mt5.check_order(
            order.symbol,
            order.side,
            order.volume,
            sl=order.sl,
            tp=order.tp,
            filling=order.filling_mode,
            comment=comment,
        )
        result = dict(result)
        result["backend"] = self.backend
        result["simulated"] = True
        return result

    async def send(self, order: OrderIntent) -> dict:
        if hasattr(self.mt5, "open_order") and hasattr(getattr(self.mt5, "_mt5", None), "order_send"):
            # Lecture du prix uniquement; aucun order_send.
            pass
        quote = await self.mt5.get_current_price(order.symbol)
        price = quote["ask"] if order.side == "buy" else quote["bid"]
        ticket = self._next_id
        self._next_id += 1
        comment = f"id:{order.decision_id}"
        deal = {
            "ticket": ticket + 1000,
            "order": ticket,
            "position_id": ticket,
            "symbol": order.symbol,
            "volume": order.volume,
            "price": price,
            "magic": self.magic,
            "comment": comment,
            "entry": 0,
        }
        position = {
            "ticket": ticket,
            "symbol": order.symbol,
            "type": "BUY" if order.side == "buy" else "SELL",
            "volume": order.volume,
            "price_open": price,
            "price_current": price,
            "sl": order.sl,
            "tp": order.tp,
            "profit": 0.0,
            "swap": 0.0,
            "commission": 0.0,
            "comment": comment,
            "time": quote.get("time"),
            "identifier": ticket,
            "magic": self.magic,
        }
        self.virtual_deals.append(deal)
        self.virtual_positions.append(position)
        return {
            "success": True,
            "ticket": ticket,
            "deal": deal["ticket"],
            "volume": order.volume,
            "price": price,
            "retcode": 10009,
            "comment": "shadow-fill",
            "partial": False,
            "backend": self.backend,
            "simulated": True,
        }

    async def orders(self, symbol: str) -> list[dict]:
        return []

    async def history_orders(self, symbol: str) -> list[dict]:
        return []

    async def history_deals(self, symbol: str) -> list[dict]:
        return [item for item in self.virtual_deals if item.get("symbol") == symbol or not symbol]

    async def positions(self, symbol: Optional[str] = None) -> list[dict]:
        items = self.virtual_positions
        if symbol:
            items = [item for item in items if item.get("symbol") == symbol]
        return list(items)

    async def close(self, ticket: int) -> dict:
        remaining = []
        closed = None
        for item in self.virtual_positions:
            if int(item["ticket"]) == int(ticket):
                closed = item
            else:
                remaining.append(item)
        self.virtual_positions = remaining
        return {"success": closed is not None, "ticket": ticket, "simulated": True}

    async def modify(self, ticket: int, sl=None, tp=None) -> dict:
        for item in self.virtual_positions:
            if int(item["ticket"]) == int(ticket):
                if sl is not None:
                    item["sl"] = sl
                if tp is not None:
                    item["tp"] = tp
                return {"success": True, "ticket": ticket, "simulated": True}
        return {"success": False, "ticket": ticket, "simulated": True}
