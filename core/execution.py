"""Service unique: intent -> check -> persist send attempt -> send -> reconcile."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

from core.ledger import Ledger
from core.mt5_execution import MT5DemoAdapter
from core.order_state import AMBIGUOUS, can_resend, reduce_events
from core.reconciliation import Reconciler
from core.types import ExecutionResult, OrderIntent, SymbolSpec

TERMINAL = {"FILLED", "PARTIAL", "REJECTED", "RECONCILED", "CANCELED", "EXPIRED"}


class ExecutionGateway:
    def __init__(
        self,
        mt5,
        ledger: Ledger,
        spec: SymbolSpec,
        magic: int,
        now: Optional[Callable[[], datetime]] = None,
        adapter=None,
        controls=None,
    ):
        self.mt5 = mt5
        self.ledger = ledger
        self.spec = spec
        self.magic = magic
        self._now = now or (lambda: datetime.now(timezone.utc))
        self.adapter = adapter or MT5DemoAdapter(mt5, spec)
        self.controls = controls
        self.reconciler = Reconciler(self.adapter, ledger, magic)

    def _comment(self, decision_id: str) -> str:
        return f"id:{decision_id}"

    def _owns(self, position: dict, decision_id: Optional[str] = None) -> bool:
        return self.reconciler._owns(position, decision_id)

    def _stops_valid(self, order: OrderIntent) -> bool:
        if order.side == "buy":
            return order.sl < order.price < order.tp
        return order.tp < order.price < order.sl

    def _client_order_id(self, order: OrderIntent) -> str:
        return order.client_order_id or f"c:{order.decision_id}"

    def _send_attempt_id(self, order: OrderIntent) -> str:
        return order.send_attempt_id or f"s:{order.decision_id}:1"

    def _block_new_entries(self, reason: str) -> None:
        if self.controls is not None:
            self.controls.halt_entries(reason)

    async def submit(self, order: OrderIntent) -> ExecutionResult:
        existing = self.ledger.last_result(order.decision_id)
        status = self.ledger.status(order.decision_id)
        view = reduce_events(
            self.ledger.events(order.decision_id),
            order.decision_id,
            requested_qty=order.volume,
        )
        if status in TERMINAL and existing is not None and not existing.ambiguous:
            return existing
        if existing is not None and existing.ambiguous:
            recovered = await self.reconciler.recover(order)
            if recovered is None:
                self._block_new_entries("AMBIGUOUS_EXPOSURE")
                return existing
            self.ledger.append(order.decision_id, "result", recovered.__dict__)
            await self._mark_reconciled(order.decision_id, recovered)
            return recovered
        if not can_resend(view) and existing is not None:
            self._block_new_entries("AMBIGUOUS_EXPOSURE")
            return existing

        client_order_id = self._client_order_id(order)
        comment = self._comment(order.decision_id)
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
                "client_order_id": client_order_id,
                "comment": comment,
                "backend": getattr(self.adapter, "backend", "mt5"),
                "simulated": bool(getattr(self.adapter, "simulated", False)),
            },
            client_order_id=client_order_id,
        )

        if not self._stops_valid(order):
            result = ExecutionResult(
                order.decision_id, "REJECTED", comment="invalid stop side"
            )
            self.ledger.append(order.decision_id, "rejected", result.__dict__)
            self.ledger.append(order.decision_id, "result", result.__dict__)
            return result

        check = await self.adapter.check(order)
        self.ledger.append(order.decision_id, "check", check, client_order_id=client_order_id)
        if not check.get("ok"):
            result = ExecutionResult(
                order.decision_id,
                "REJECTED",
                comment=str(check.get("comment") or "order_check"),
                retcode=check.get("retcode"),
            )
            self.ledger.append(order.decision_id, "rejected", result.__dict__)
            self.ledger.append(order.decision_id, "result", result.__dict__)
            return result

        if not getattr(self.adapter, "simulated", False) and not getattr(
            self.mt5, "is_trading_armed", False
        ):
            result = ExecutionResult(
                order.decision_id, "REJECTED", comment="not armed"
            )
            self.ledger.append(order.decision_id, "rejected", result.__dict__)
            self.ledger.append(order.decision_id, "result", result.__dict__)
            return result

        send_attempt_id = self._send_attempt_id(order)
        try:
            persisted = self.ledger.append(
                order.decision_id,
                "send_attempt_started",
                {
                    "send_attempt_id": send_attempt_id,
                    "client_order_id": client_order_id,
                },
                event_id=f"{order.decision_id}:send_attempt_started:{send_attempt_id}",
                client_order_id=client_order_id,
                send_attempt_id=send_attempt_id,
            )
        except Exception:
            result = ExecutionResult(
                order.decision_id, "REJECTED", comment="ledger persist failed"
            )
            return result
        if not persisted:
            existing_attempt = any(
                item["kind"] == "send_attempt_started"
                for item in self.ledger.events(order.decision_id)
            )
            if not existing_attempt:
                result = ExecutionResult(
                    order.decision_id, "REJECTED", comment="ledger persist failed"
                )
                self.ledger.append(order.decision_id, "result", result.__dict__)
                return result

        try:
            sent = await self.adapter.send(order)
        except TimeoutError:
            recovered = await self.reconciler.recover(order)
            self.ledger.append(
                order.decision_id,
                "timeout",
                {"after_send": recovered is not None, "send_attempt_id": send_attempt_id},
                send_attempt_id=send_attempt_id,
            )
            if recovered is None:
                result = ExecutionResult(order.decision_id, "UNKNOWN", ambiguous=True)
                self.ledger.append(order.decision_id, "result", result.__dict__)
                self._block_new_entries("AMBIGUOUS_EXPOSURE")
                return result
            self.ledger.append(order.decision_id, "result", recovered.__dict__)
            await self._mark_reconciled(order.decision_id, recovered)
            return recovered

        self.ledger.append(order.decision_id, "send", sent, client_order_id=client_order_id)
        if not sent.get("success"):
            recovered = await self.reconciler.recover(order)
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
            self._block_new_entries("AMBIGUOUS_EXPOSURE")
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
        fill_kind = "fill_partial" if status_name == "PARTIAL" else "fill_final"
        self.ledger.append(
            order.decision_id,
            fill_kind,
            {
                "volume": result.volume,
                "deal_ticket": result.deal_id,
                "price": result.price,
            },
            deal_ticket=result.deal_id,
            order_ticket=result.order_id,
            position_id=result.position_id,
        )
        if status_name == "PARTIAL":
            filling = order.filling_mode
            api = getattr(self.mt5, "_mt5", None)
            ioc = getattr(api, "ORDER_FILLING_IOC", 1) if api is not None else 1
            ret = getattr(api, "ORDER_FILLING_RETURN", 3) if api is not None else 3
            if filling == ioc:
                self.ledger.append(
                    order.decision_id,
                    "canceled",
                    {"remainder": round(order.volume - result.volume, 8), "policy": "IOC"},
                )
            elif filling == getattr(api, "ORDER_FILLING_FOK", 2) if api is not None else 2:
                self.ledger.append(
                    order.decision_id,
                    "timeout",
                    {"anomaly": "FOK_PARTIAL", "send_attempt_id": send_attempt_id},
                )
                result = ExecutionResult(
                    order.decision_id,
                    "UNKNOWN",
                    order_id=result.order_id,
                    deal_id=result.deal_id,
                    position_id=result.position_id,
                    volume=result.volume,
                    price=result.price,
                    comment="FOK partial is protocol anomaly",
                    ambiguous=True,
                )
                self._block_new_entries("FOK_PARTIAL")
        self.ledger.append(
            order.decision_id,
            "position_opened",
            {"position_id": result.position_id, "volume": result.volume},
            position_id=result.position_id,
        )
        self.ledger.append(order.decision_id, "accepted", {"order_id": result.order_id})
        self.ledger.append(order.decision_id, "result", result.__dict__)
        await self._mark_reconciled(order.decision_id, result)
        return result

    async def _recover(self, order: OrderIntent) -> Optional[ExecutionResult]:
        return await self.reconciler.recover(order)

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
            order_ticket=result.order_id,
            position_id=result.position_id,
        )

    async def reconcile(self) -> dict:
        return await self.reconciler.snapshot()

    async def close_owned(self, ticket: int) -> dict:
        if self.controls is not None and not self.controls.state.position_management_enabled:
            return {"success": False, "error": "position management disabled"}
        return await self.adapter.close(ticket)

    async def modify_owned(self, ticket: int, sl=None, tp=None) -> dict:
        if self.controls is not None and not self.controls.state.position_management_enabled:
            return {"success": False, "error": "position management disabled"}
        return await self.adapter.modify(ticket, sl=sl, tp=tp)
