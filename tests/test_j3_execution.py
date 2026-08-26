from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from config import MAGIC_NUMBER
from core.execution import ExecutionGateway
from core.ledger import Ledger
from core.types import OrderIntent, SymbolSpec
from fakes import FakeMT5
from mt5_client import MT5Client


GOLD = SymbolSpec(
    name="XAUUSD",
    digits=2,
    point=0.01,
    trade_tick_size=0.01,
    trade_tick_value=1.0,
    trade_tick_value_profit=1.0,
    trade_tick_value_loss=1.0,
    trade_contract_size=100.0,
    trade_calc_mode=0,
    currency_profit="USD",
    currency_margin="USD",
    volume_min=0.01,
    volume_max=5.0,
    volume_step=0.01,
    volume_limit=10.0,
    trade_stops_level=10,
    trade_freeze_level=0,
    filling_mode=FakeMT5.ORDER_FILLING_IOC,
)


def _order(decision_id: str = "dec-1", **kwargs) -> OrderIntent:
    payload = dict(
        decision_id=decision_id,
        symbol="XAUUSD",
        side="buy",
        volume=0.01,
        price=2500.2,
        sl=2490.0,
        tp=2520.0,
        filling_mode=FakeMT5.ORDER_FILLING_IOC,
        comment="test",
    )
    payload.update(kwargs)
    return OrderIntent(**payload)


def _client(api=None, armed=True):
    client = MT5Client(mt5_api=api or FakeMT5(), trading_mode="demo")
    if armed:
        client.arm_trading()
    return client


def _gateway(tmp_path: Path, api=None, client=None):
    ledger = Ledger(tmp_path / "ledger.sqlite")
    return ExecutionGateway(
        mt5=client or _client(api),
        ledger=ledger,
        spec=GOLD,
        magic=MAGIC_NUMBER,
        now=lambda: datetime(2026, 8, 25, 15, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_submit_checks_then_sends_once(tmp_path: Path) -> None:
    api = FakeMT5()
    gateway = _gateway(tmp_path, api)
    result = await gateway.submit(_order())

    assert result.status == "FILLED"
    assert result.ambiguous is False
    assert len(api.check_requests) == 1
    assert len(api.order_requests) == 1
    assert gateway.ledger.status("dec-1") == "RECONCILED"


@pytest.mark.asyncio
async def test_duplicate_decision_id_does_not_resend(tmp_path: Path) -> None:
    api = FakeMT5()
    gateway = _gateway(tmp_path, api)
    first = await gateway.submit(_order())
    second = await gateway.submit(_order())

    assert first.status == "FILLED"
    assert second.status in {"FILLED", "RECONCILED"}
    assert len(api.order_requests) == 1


@pytest.mark.asyncio
async def test_check_reject_never_sends(tmp_path: Path) -> None:
    api = FakeMT5(check_retcode=FakeMT5.TRADE_RETCODE_INVALID_FILL)
    api.filling = FakeMT5.ORDER_FILLING_FOK
    gateway = _gateway(tmp_path, api)
    result = await gateway.submit(_order(filling_mode=FakeMT5.ORDER_FILLING_FOK))

    assert result.status == "REJECTED"
    assert api.order_requests == []


@pytest.mark.asyncio
async def test_timeout_after_send_recovers_without_duplicate(tmp_path: Path) -> None:
    api = FakeMT5()
    api.timeout_send = True
    client = _client(api)
    gateway = _gateway(tmp_path, client=client)
    result = await gateway.submit(_order())

    assert result.status in {"FILLED", "RECONCILED"}
    assert result.ambiguous is False
    assert len(api.order_requests) == 1
    api.timeout_send = False
    again = await gateway.submit(_order())
    assert len(api.order_requests) == 1
    assert again.status in {"FILLED", "RECONCILED"}


@pytest.mark.asyncio
async def test_timeout_before_send_does_not_invent_fill(tmp_path: Path) -> None:
    api = FakeMT5()
    api.fail_before_send = True
    gateway = _gateway(tmp_path, api)
    result = await gateway.submit(_order())

    assert result.status == "UNKNOWN"
    assert result.ambiguous is True
    assert api.order_requests == []


@pytest.mark.asyncio
async def test_partial_fill_is_recorded(tmp_path: Path) -> None:
    api = FakeMT5()
    api.partial_volume = 0.01
    api.send_volume = 0.02
    gateway = _gateway(tmp_path, api)
    result = await gateway.submit(_order(volume=0.02))

    assert result.status in {"PARTIAL", "RECONCILED"}
    assert result.volume == 0.01


@pytest.mark.asyncio
async def test_restart_reconciles_open_position(tmp_path: Path) -> None:
    api = FakeMT5()
    first = _gateway(tmp_path, api)
    await first.submit(_order())
    second = _gateway(tmp_path, api)
    report = await second.reconcile()

    assert report["unexplained"] == 0
    assert report["owned_positions"] >= 1


@pytest.mark.asyncio
async def test_foreign_magic_is_ignored(tmp_path: Path) -> None:
    api = FakeMT5()
    api.positions = [
        SimpleNamespace(
            ticket=9,
            symbol="XAUUSD",
            type=0,
            volume=0.01,
            price_open=2500.0,
            price_current=2501.0,
            sl=2490.0,
            tp=2520.0,
            profit=1.0,
            swap=0.0,
            commission=0.0,
            comment="other",
            time=0,
            identifier=9,
            magic=1,
        )
    ]
    gateway = _gateway(tmp_path, api)
    report = await gateway.reconcile()
    assert report["foreign_positions"] == 1
    assert report["owned_positions"] == 0


@pytest.mark.asyncio
async def test_wrong_stop_side_never_sends(tmp_path: Path) -> None:
    api = FakeMT5()
    gateway = _gateway(tmp_path, api)
    result = await gateway.submit(_order(sl=2510.0, tp=2480.0))
    assert result.status == "REJECTED"
    assert api.order_requests == []


@pytest.mark.asyncio
async def test_timeout_recovers_from_deals_without_position(tmp_path: Path) -> None:
    api = FakeMT5()
    api.timeout_send = True
    api.drop_position_after_send = True
    gateway = _gateway(tmp_path, api)
    result = await gateway.submit(_order())
    assert result.status in {"FILLED", "PARTIAL", "RECONCILED"}
    assert result.ambiguous is False
    assert len(api.order_requests) == 1
    assert len(api.deals) == 1


@pytest.mark.asyncio
async def test_ambiguous_timeout_does_not_resend(tmp_path: Path) -> None:
    api = FakeMT5()
    api.fail_before_send = True
    gateway = _gateway(tmp_path, api)
    first = await gateway.submit(_order())
    second = await gateway.submit(_order())
    assert first.ambiguous is True
    assert second.ambiguous is True
    assert api.order_requests == []


@pytest.mark.asyncio
async def test_ioc_partial_records_canceled_remainder(tmp_path: Path) -> None:
    api = FakeMT5()
    api.partial_volume = 0.01
    gateway = _gateway(tmp_path, api)
    result = await gateway.submit(_order(volume=0.02))
    assert result.volume == 0.01
    kinds = [item["kind"] for item in gateway.ledger.events("dec-1")]
    assert "fill_partial" in kinds
    assert "canceled" in kinds


@pytest.mark.asyncio
async def test_truncated_comment_still_recovers_via_mapping(tmp_path: Path) -> None:
    api = FakeMT5()
    api.timeout_send = True
    api.truncate_comment = 4
    gateway = _gateway(tmp_path, api)
    result = await gateway.submit(_order())
    assert result.status in {"FILLED", "PARTIAL", "RECONCILED"}
    assert result.ambiguous is False


@pytest.mark.asyncio
async def test_persist_failure_before_send_never_sends(tmp_path: Path) -> None:
    api = FakeMT5()
    ledger = Ledger(tmp_path / "ledger.sqlite")
    original = ledger.append

    def boom(decision_id, kind, payload, **kwargs):
        if kind == "send_attempt_started":
            raise RuntimeError("disk full")
        return original(decision_id, kind, payload, **kwargs)

    ledger.append = boom  # type: ignore[method-assign]
    gateway = ExecutionGateway(
        mt5=_client(api),
        ledger=ledger,
        spec=GOLD,
        magic=MAGIC_NUMBER,
        now=lambda: datetime(2026, 8, 25, 15, tzinfo=timezone.utc),
    )
    result = await gateway.submit(_order())
    assert result.status == "REJECTED"
    assert api.order_requests == []
