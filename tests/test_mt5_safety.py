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
async def test_mt5_calls_are_serialized_across_client_instances() -> None:
    first_api = FakeMT5(FakeMT5.ACCOUNT_TRADE_MODE_DEMO)
    second_api = FakeMT5(FakeMT5.ACCOUNT_TRADE_MODE_DEMO)
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

    first_api.symbol_info_tick = slow_tick
    second_api.symbol_info_tick = slow_tick
    first = MT5Client(mt5_api=first_api)
    second = MT5Client(mt5_api=second_api)

    await asyncio.gather(
        first.get_current_price("XAUUSD"),
        second.get_current_price("EURUSD"),
    )

    assert max_active_calls == 1


@pytest.mark.asyncio
async def test_shared_executor_can_shutdown_and_restart_cleanly() -> None:
    api = FakeMT5(FakeMT5.ACCOUNT_TRADE_MODE_DEMO)
    client = MT5Client(mt5_api=api)
    await client.get_current_price("XAUUSD")

    MT5Client.shutdown_shared_executor()

    assert not any(
        thread.name.startswith("mt5-client") and thread.is_alive()
        for thread in threading.enumerate()
    )
    price = await client.get_current_price("XAUUSD")
    assert price["bid"] == 2500.0


@pytest.mark.asyncio
async def test_closed_profit_history_runs_through_serialized_client() -> None:
    api = FakeMT5(FakeMT5.ACCOUNT_TRADE_MODE_DEMO)
    api.DEAL_ENTRY_OUT = 1
    history_calls: list[tuple[int, str]] = []

    def history_deals_get(from_date, to_date, *, position: int):
        history_calls.append((position, threading.current_thread().name))
        return [
            SimpleNamespace(entry=0, profit=0.0),
            SimpleNamespace(entry=api.DEAL_ENTRY_OUT, profit=7.5),
        ]

    api.history_deals_get = history_deals_get
    client = MT5Client(mt5_api=api)

    profit = await client.get_closed_profit(123)

    assert profit == 7.5
    assert history_calls == [(123, "mt5-client_0")]


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


@pytest.mark.asyncio
async def test_disarm_after_price_read_prevents_order_send() -> None:
    api = FakeMT5(FakeMT5.ACCOUNT_TRADE_MODE_DEMO)
    client = MT5Client(mt5_api=api, trading_mode="demo")
    client.arm_trading()
    original_get_price = client.get_current_price

    async def get_price_then_disarm(symbol: str) -> dict:
        price = await original_get_price(symbol)
        client.disarm_trading()
        return price

    client.get_current_price = get_price_then_disarm

    result = await client.open_order("XAUUSD", "buy", 0.01)

    assert result["success"] is False
    assert "armement" in result["error"].lower()
    assert api.order_requests == []


@pytest.mark.asyncio
async def test_account_change_after_price_read_prevents_order_send() -> None:
    api = FakeMT5(FakeMT5.ACCOUNT_TRADE_MODE_DEMO)
    client = MT5Client(mt5_api=api, trading_mode="demo")
    client.arm_trading()
    original_get_price = client.get_current_price

    async def get_price_then_switch_account(symbol: str) -> dict:
        price = await original_get_price(symbol)
        api.account_trade_mode = FakeMT5.ACCOUNT_TRADE_MODE_REAL
        return price

    client.get_current_price = get_price_then_switch_account

    result = await client.open_order("XAUUSD", "buy", 0.01)

    assert result["success"] is False
    assert "compte demo" in result["error"].lower()
    assert api.order_requests == []


@pytest.mark.asyncio
async def test_mode_change_after_price_read_prevents_order_send() -> None:
    api = FakeMT5(FakeMT5.ACCOUNT_TRADE_MODE_DEMO)
    client = MT5Client(mt5_api=api, trading_mode="demo")
    client.arm_trading()
    original_get_price = client.get_current_price

    async def get_price_then_disable(symbol: str) -> dict:
        price = await original_get_price(symbol)
        client.trading_mode = "off"
        return price

    client.get_current_price = get_price_then_disable

    result = await client.open_order("XAUUSD", "buy", 0.01)

    assert result["success"] is False
    assert "lecture seule" in result["error"].lower()
    assert api.order_requests == []
