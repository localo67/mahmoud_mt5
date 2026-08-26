"""Reconciliation autoritaire: tickets persistes, ordres, historique, deals, positions."""

from __future__ import annotations

from typing import Optional

from core.types import ExecutionResult, OrderIntent


def filled_from_deals(deals: list[dict]) -> tuple[float, list[int], Optional[int], Optional[int]]:
    unique: dict[int, dict] = {}
    for deal in deals:
        ticket = deal.get("ticket")
        if ticket is None:
            continue
        unique[int(ticket)] = deal
    volume = sum(float(item.get("volume") or 0.0) for item in unique.values())
    tickets = list(unique.keys())
    position_id = None
    order_id = None
    if unique:
        first = next(iter(unique.values()))
        position_id = first.get("position_id") or first.get("position")
        order_id = first.get("order")
    return round(volume, 8), tickets, order_id, position_id


class Reconciler:
    def __init__(self, adapter, ledger, magic: int, comment_prefix: str = "id:"):
        self.adapter = adapter
        self.ledger = ledger
        self.magic = int(magic)
        self.comment_prefix = comment_prefix

    def _owns(self, item: dict, decision_id: Optional[str] = None) -> bool:
        if int(item.get("magic") or 0) != self.magic:
            return False
        comment = str(item.get("comment") or "")
        mapped = self.ledger.mapping(decision_id) if decision_id else {}
        if decision_id is None:
            return True
        token = f"{self.comment_prefix}{decision_id}"
        if token in comment:
            return True
        order_ticket = mapped.get("order_ticket")
        if order_ticket is not None and int(item.get("ticket") or item.get("order") or 0) == int(order_ticket):
            return True
        if item.get("order") is not None and order_ticket is not None:
            if int(item["order"]) == int(order_ticket):
                return True
        deal_tickets = mapped.get("deal_tickets") or []
        if item.get("ticket") in deal_tickets:
            return True
        client_order_id = mapped.get("client_order_id")
        if client_order_id and client_order_id in comment:
            return True
        return False

    async def recover(self, order: OrderIntent) -> Optional[ExecutionResult]:
        mapping = self.ledger.mapping(order.decision_id)
        deals = await self.adapter.history_deals(order.symbol)
        owned_deals = [item for item in deals if self._owns(item, order.decision_id)]
        if mapping.get("order_ticket") is not None:
            owned_deals = owned_deals or [
                item
                for item in deals
                if int(item.get("order") or 0) == int(mapping["order_ticket"])
            ]
        if not owned_deals:
            claimed = {
                int(event["deal_ticket"])
                for event in self.ledger.all_events()
                if event.get("deal_ticket") is not None
            }
            unclaimed = [
                item
                for item in deals
                if int(item.get("magic") or 0) == self.magic
                and int(item.get("ticket") or 0) not in claimed
            ]
            if len(unclaimed) == 1:
                owned_deals = unclaimed
        volume, deal_tickets, order_id, position_id = filled_from_deals(owned_deals)
        history_orders = await self.adapter.history_orders(order.symbol)
        owned_history = [item for item in history_orders if self._owns(item, order.decision_id)]
        active = await self.adapter.orders(order.symbol)
        owned_active = [item for item in active if self._owns(item, order.decision_id)]
        positions = await self.adapter.positions(order.symbol)
        owned_positions = [item for item in positions if self._owns(item, order.decision_id)]

        if owned_positions:
            item = owned_positions[0]
            filled = float(item.get("volume") or volume or 0.0)
            status = "PARTIAL" if filled + 1e-12 < order.volume else "FILLED"
            return ExecutionResult(
                order.decision_id,
                status,
                order_id=item.get("ticket") or order_id,
                deal_id=deal_tickets[0] if deal_tickets else None,
                position_id=item.get("identifier") or item.get("ticket") or position_id,
                volume=filled,
                price=float(item.get("price_open") or item.get("price") or 0.0),
                comment=str(item.get("comment") or ""),
                ambiguous=False,
            )

        if volume > 0:
            status = "PARTIAL" if volume + 1e-12 < order.volume else "FILLED"
            return ExecutionResult(
                order.decision_id,
                status,
                order_id=order_id or mapping.get("order_ticket"),
                deal_id=deal_tickets[0] if deal_tickets else None,
                position_id=position_id,
                volume=volume,
                price=float((owned_deals[0].get("price") if owned_deals else 0.0) or 0.0),
                comment=str((owned_deals[0].get("comment") if owned_deals else "") or ""),
                ambiguous=False,
            )

        if owned_active or owned_history:
            item = (owned_active or owned_history)[0]
            return ExecutionResult(
                order.decision_id,
                "UNKNOWN",
                order_id=item.get("ticket") or item.get("order"),
                comment=str(item.get("comment") or ""),
                ambiguous=True,
            )
        return None

    async def snapshot(self, symbol: Optional[str] = None) -> dict:
        positions = await self.adapter.positions(symbol)
        owned = [item for item in positions if int(item.get("magic") or 0) == self.magic]
        foreign = [item for item in positions if int(item.get("magic") or 0) != self.magic]
        unexplained = 0
        external = 0
        for item in owned:
            comment = str(item.get("comment") or "")
            if "id:" not in comment:
                unexplained += 1
                external += 1
        deals = await self.adapter.history_deals(symbol or "")
        return {
            "owned_positions": len(owned),
            "foreign_positions": len(foreign),
            "unexplained": unexplained,
            "external_recovered": external,
            "deal_count": len(deals),
            "gaps": unexplained,
        }
