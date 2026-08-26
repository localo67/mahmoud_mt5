"""Gateway unique: intent -> risque deja decide -> order_check -> send -> reconcile."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

from core.ledger import Ledger
from core.types import ExecutionResult, OrderIntent, SymbolSpec


TERMINAL = {"FILLED", "PARTIAL", "REJECTED", "RECONCILED"}


class ExecutionGateway:
    def __init__(
        self,
        mt5,
        ledger: Ledger,
        spec: SymbolSpec,
        magic: int,
        now: Optional[Callable[[], datetime]] = None,
    ):
        self.mt5 = mt5
        self.ledger = ledger
        self.spec = spec
        self.magic = magic
        self._now = now or (lambda: datetime.now(timezone.utc))

    def _comment(self, decision_id: str) -> str:
        return f"id:{decision_id}"

    def _owns(self, position: dict, decision_id: Optional[str] = None) -> bool:
        if int(position.get("magic") or 0) != int(self.magic):
            return False
        if decision_id is None:
            return True
        return self._comment(decision_id) in str(position.get("comment") or "")

    def _stops_valid(self, order: OrderIntent) -> bool:
        if order.side == "buy":
            return order.sl < order.price < order.tp
        return order.tp < order.price < order.sl

    async def submit(self, order: OrderIntent) -> ExecutionResult:
        existing = self.ledger.last_result(order.decision_id)
        status = self.ledger.status(order.decision_id)
        if status in TERMINAL:
            if existing is not None:
                return existing
            return ExecutionResult(order.decision_id, status)

        self.ledger.append(
            order.decision_id,
            "intent",
            {
                "symbol": order.symbol,
                "side": order.side,
                "volume": order.volume,
                "price": order.price,
                "sl": order.sl,
                "tp": order.tp,
            },
        )

        if not self._stops_valid(order):
            result = ExecutionResult(
                order.decision_id, "REJECTED", comment="invalid stop side"
            )
            self.ledger.append(order.decision_id, "result", result.__dict__)
            return result

        filling = order.filling_mode if order.filling_mode is not None else self.spec.filling_mode
        check = await self.mt5.check_order(
            order.symbol,
            order.side,
            order.volume,
            sl=order.sl,
            tp=order.tp,
            filling=filling,
            comment=self._comment(order.decision_id),
        )
        self.ledger.append(order.decision_id, "check", check)
        if not check.get("ok"):
            result = ExecutionResult(
                order.decision_id,
                "REJECTED",
                comment=str(check.get("comment") or "order_check"),
                retcode=check.get("retcode"),
            )
            self.ledger.append(order.decision_id, "result", result.__dict__)
            return result

        try:
            sent = await self.mt5.open_order(
                symbol=order.symbol,
                order_type=order.side,
                volume=order.volume,
                sl=order.sl,
                tp=order.tp,
                comment=self._comment(order.decision_id),
                filling=filling,
            )
        except TimeoutError:
            recovered = await self._recover(order)
            self.ledger.append(order.decision_id, "timeout", {"after_send": recovered is not None})
            if recovered is None:
                result = ExecutionResult(order.decision_id, "UNKNOWN", ambiguous=True)
                self.ledger.append(order.decision_id, "result", result.__dict__)
                return result
            self.ledger.append(order.decision_id, "result", recovered.__dict__)
            await self._mark_reconciled(order.decision_id, recovered)
            return recovered

        self.ledger.append(order.decision_id, "send", sent)
        if not sent.get("success"):
            recovered = await self._recover(order)
            if recovered is not None:
                await self._mark_reconciled(order.decision_id, recovered)
                return recovered
            result = ExecutionResult(
                order.decision_id,
                "UNKNOWN",
                comment=str(sent.get("error") or ""),
                retcode=sent.get("retcode"),
                ambiguous=True,
            )
            self.ledger.append(order.decision_id, "result", result.__dict__)
            return result

        status_name = "PARTIAL" if sent.get("partial") else "FILLED"
        result = ExecutionResult(
            order.decision_id,
            status_name,
            order_id=sent.get("ticket"),
            deal_id=sent.get("deal"),
            position_id=sent.get("ticket"),
            volume=float(sent.get("volume") or order.volume),
            price=float(sent.get("price") or order.price),
            comment=str(sent.get("comment") or ""),
            retcode=sent.get("retcode"),
        )
        self.ledger.append(order.decision_id, "result", result.__dict__)
        await self._mark_reconciled(order.decision_id, result)
        return result

    async def _recover(self, order: OrderIntent) -> Optional[ExecutionResult]:
        positions = await self.mt5.get_positions(symbol=order.symbol)
        owned = [item for item in positions if self._owns(item, order.decision_id)]
        if not owned:
            return None
        item = owned[0]
        status_name = "PARTIAL" if float(item["volume"]) + 1e-12 < order.volume else "FILLED"
        return ExecutionResult(
            order.decision_id,
            status_name,
            order_id=item.get("ticket"),
            position_id=item.get("identifier") or item.get("ticket"),
            volume=float(item["volume"]),
            price=float(item.get("price_open") or 0.0),
            comment=str(item.get("comment") or ""),
            ambiguous=False,
        )

    async def _mark_reconciled(self, decision_id: str, result: ExecutionResult) -> None:
        self.ledger.append(
            decision_id,
            "reconcile",
            {
                "ok": True,
                "order_id": result.order_id,
                "position_id": result.position_id,
                "volume": result.volume,
            },
        )

    async def reconcile(self) -> dict:
        positions = await self.mt5.get_positions()
        owned = [item for item in positions if self._owns(item)]
        foreign = [item for item in positions if int(item.get("magic") or 0) != int(self.magic)]
        unexplained = 0
        for item in owned:
            comment = str(item.get("comment") or "")
            if "id:" not in comment:
                unexplained += 1
        return {
            "owned_positions": len(owned),
            "foreign_positions": len(foreign),
            "unexplained": unexplained,
        }
