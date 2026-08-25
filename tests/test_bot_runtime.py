import pytest

import bot


class InitializableClient:
    def __init__(self):
        self.initialize_calls = 0

    async def initialize(self) -> bool:
        self.initialize_calls += 1
        return True


@pytest.mark.asyncio
async def test_off_runtime_skips_mt5_initialization() -> None:
    client = InitializableClient()
    initializer = getattr(bot, "initialize_mt5_for_runtime", None)

    assert initializer is not None
    result = await initializer(client, "off")

    assert result is None
    assert client.initialize_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["shadow", "demo", "live"])
async def test_mt5_runtime_modes_initialize_client(mode: str) -> None:
    client = InitializableClient()
    initializer = getattr(bot, "initialize_mt5_for_runtime", None)

    assert initializer is not None
    result = await initializer(client, mode)

    assert result is True
    assert client.initialize_calls == 1
