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


def test_arm_demo_flag_requires_demo_mode() -> None:
    args = bot.parse_args([])
    assert args.arm_demo is False
    args = bot.parse_args(["--arm-demo"])
    assert args.arm_demo is True

    class FakeClient:
        trading_mode = "off"

        def arm_trading(self):
            raise AssertionError("ne doit pas armer hors demo")

    assert bot.arm_demo_if_requested(FakeClient(), True) is False


def test_arm_demo_flag_arms_demo_client() -> None:
    class FakeClient:
        trading_mode = "demo"
        armed = False

        def arm_trading(self):
            self.armed = True

    client = FakeClient()
    assert bot.arm_demo_if_requested(client, True) is True
    assert client.armed is True
