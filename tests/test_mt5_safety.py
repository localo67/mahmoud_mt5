import asyncio
import threading
import time
from types import SimpleNamespace
from typing import Awaitable, Callable

import pytest

from mt5_client import MT5Client


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_REAL = 2
    POSITION_TYPE_BUY = 0
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_SLTP = 6
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    TRADE_RETCODE_DONE = 10009

    def __init__(self, account_trade_mode: int):
        self.account_trade_mode = account_trade_mode
        self.order_requests: list[dict] = []

    def account_info(self):
        return SimpleNamespace(trade_mode=self.account_trade_mode)

    def positions_get(self, **kwargs):
        return [
            SimpleNamespace(
                ticket=123,
                symbol="XAUUSD",
                type=self.POSITION_TYPE_BUY,
                volume=0.01,
                price_open=2500.0,
                price_current=2501.0,
                sl=2490.0,
                tp=2520.0,
                profit=1.0,
                swap=0.0,
                commission=0.0,
                comment="test",
                time=0,
                identifier=123,
            )
        ]

    def symbol_info_tick(self, symbol: str):
        return SimpleNamespace(bid=2500.0, ask=2500.2, time=0)

    def order_send(self, request: dict):
        self.order_requests.append(request)
        return SimpleNamespace(
            retcode=self.TRADE_RETCODE_DONE,
            order=987,
            comment="done",
        )

    def last_error(self):
        return (0, "ok")


MutationCall = Callable[[MT5Client], Awaitable[dict]]


async def _open(client: MT5Client) -> dict:
    return await client.open_order("XAUUSD", "buy", 0.01)


async def _close(client: MT5Client) -> dict:
    return await client.close_position(123)


async def _modify(client: MT5Client) -> dict:
    return await client.modify_position(123, sl=2495.0)


async def _close_all(client: MT5Client) -> dict:
    return await client.close_all_positions()


MUTATIONS: list[tuple[str, MutationCall]] = [
    ("open_order", _open),
    ("close_position", _close),
    ("modify_position", _modify),
    ("close_all_positions", _close_all),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation_name,mutation", MUTATIONS)
@pytest.mark.parametrize("armed", [False, True])
@pytest.mark.parametrize("account_kind", ["real", "demo"])
@pytest.mark.parametrize("trading_mode", ["off", "shadow", "demo", "live"])
async def test_mutation_guard_matrix(
    mutation_name: str,
    mutation: MutationCall,
    armed: bool,
    account_kind: str,
    trading_mode: str,
) -> None:
    account_mode = (
        FakeMT5.ACCOUNT_TRADE_MODE_DEMO
        if account_kind == "demo"
        else FakeMT5.ACCOUNT_TRADE_MODE_REAL
    )
    api = FakeMT5(account_mode)
    client = MT5Client(mt5_api=api, trading_mode=trading_mode)
    if armed:
        client.arm_trading()

    result = await mutation(client)

    allowed = trading_mode == "demo" and account_kind == "demo" and armed
    assert result["success"] is allowed, mutation_name
    assert len(api.order_requests) == (1 if allowed else 0), mutation_name
    if not allowed:
        assert "refus" in result["error"].lower()
    if trading_mode == "live":
        assert "non implemente" in result["error"].lower()


def test_trading_is_disarmed_for_every_new_client() -> None:
    api = FakeMT5(FakeMT5.ACCOUNT_TRADE_MODE_DEMO)

    first = MT5Client(mt5_api=api, trading_mode="demo")
    first.arm_trading()
    second = MT5Client(mt5_api=api, trading_mode="demo")

    assert first.is_trading_armed is True
    assert second.is_trading_armed is False


@pytest.mark.asyncio
async def test_all_mt5_calls_are_serialized() -> None:
    api = FakeMT5(FakeMT5.ACCOUNT_TRADE_MODE_DEMO)
    lock = threading.Lock()
    active_calls = 0
    max_active_calls = 0

    def slow_tick(symbol: str):
        nonlocal active_calls, max_active_calls
        with lock:
            active_calls += 1
            max_active_calls = max(max_active_calls, active_calls)
        time.sleep(0.05)
        with lock:
            active_calls -= 1
        return SimpleNamespace(bid=2500.0, ask=2500.2, time=0)

    api.symbol_info_tick = slow_tick
    client = MT5Client(mt5_api=api)

    await asyncio.gather(
        client.get_current_price("XAUUSD"),
        client.get_current_price("EURUSD"),
    )

    assert max_active_calls == 1


@pytest.mark.asyncio
async def test_last_error_also_runs_on_the_dedicated_mt5_thread() -> None:
    api = FakeMT5(FakeMT5.ACCOUNT_TRADE_MODE_DEMO)
    call_threads: list[str] = []

    def failed_order_send(request: dict):
        call_threads.append(threading.current_thread().name)
        return None

    def last_error():
        call_threads.append(threading.current_thread().name)
        return (500, "failure")

    api.order_send = failed_order_send
    api.last_error = last_error
    client = MT5Client(mt5_api=api, trading_mode="demo")
    client.arm_trading()

    result = await client.open_order("XAUUSD", "buy", 0.01)

    assert result["success"] is False
    assert len(set(call_threads)) == 1
    assert call_threads[0].startswith("mt5-client")
