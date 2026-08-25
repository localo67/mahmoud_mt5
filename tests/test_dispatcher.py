import pytest

from tools.dispatcher import Dispatcher


MUTATING_ACTIONS = [
    {
        "function": "open_position",
        "arguments": {"symbol": "XAUUSD", "order_type": "buy", "volume": 0.01},
    },
    {"function": "close_position", "arguments": {"ticket": 123}},
    {"function": "close_all_positions", "arguments": {}},
    {"function": "modify_position", "arguments": {"ticket": 123, "sl": 2490.0}},
]


class MutationTrap:
    def __init__(self):
        self.calls: list[str] = []

    async def check_connection(self):
        self.calls.append("check_connection")
        return True

    async def open_order(self, **kwargs):
        self.calls.append("open_order")
        return {"success": True}

    async def close_position(self, **kwargs):
        self.calls.append("close_position")
        return {"success": True}

    async def close_all_positions(self, **kwargs):
        self.calls.append("close_all_positions")
        return {"success": True, "closed": 0}

    async def modify_position(self, **kwargs):
        self.calls.append("modify_position")
        return {"success": True}


@pytest.mark.asyncio
@pytest.mark.parametrize("action", MUTATING_ACTIONS)
async def test_dispatcher_refuses_llm_mutations_without_any_mt5_call(action: dict) -> None:
    mt5 = MutationTrap()
    dispatcher = Dispatcher(mt5)

    response = await dispatcher.execute(action)

    assert "lecture seule" in response.lower()
    assert "refus" in response.lower()
    assert mt5.calls == []


class ReadOnlyMT5:
    def __init__(self):
        self.calls: list[str] = []

    async def check_connection(self):
        self.calls.append("check_connection")
        return True

    async def get_account_info(self):
        self.calls.append("get_account_info")
        return {
            "login": 123,
            "name": "Demo",
            "server": "Broker-Demo",
            "currency": "USD",
            "balance": 10_000.0,
            "equity": 10_010.0,
            "margin": 10.0,
            "free_margin": 10_000.0,
            "leverage": 100,
            "margin_level": 100_000.0,
        }


@pytest.mark.asyncio
async def test_dispatcher_keeps_account_read_available() -> None:
    mt5 = ReadOnlyMT5()
    dispatcher = Dispatcher(mt5)

    response = await dispatcher.execute(
        {"function": "get_account_info", "arguments": {}}
    )

    assert "10,000.00" in response
    assert mt5.calls == ["check_connection", "get_account_info"]
