from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from handlers.commands import auto_command, reset_command
from handlers.messages import handle_callback


def _update(text_sink: list[str]):
    message = SimpleNamespace(
        reply_text=AsyncMock(side_effect=lambda text, **kwargs: text_sink.append(text))
    )
    return SimpleNamespace(message=message)


@pytest.mark.asyncio
async def test_auto_command_does_not_enable_engine() -> None:
    texts: list[str] = []
    engine = SimpleNamespace(enabled=False, set_enabled=AsyncMock())
    context = SimpleNamespace(args=["on"], bot_data={"auto_engine": engine})
    await auto_command(_update(texts), context)
    engine.set_enabled.assert_not_called()
    assert "lecture seule" in texts[0].lower()


@pytest.mark.asyncio
async def test_reset_command_does_not_clear_kill_switch() -> None:
    texts: list[str] = []
    engine = SimpleNamespace(reset_risk=lambda: "Reset refuse: kill switch")
    context = SimpleNamespace(bot_data={"auto_engine": engine})
    await reset_command(_update(texts), context)
    assert "refuse" in texts[0].lower()


@pytest.mark.asyncio
async def test_auto_callback_does_not_enable_engine() -> None:
    engine = SimpleNamespace(enabled=False, set_enabled=AsyncMock())
    query = SimpleNamespace(
        data="auto_on",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(bot_data={"auto_engine": engine, "mt5_client": None, "dispatcher": None})
    await handle_callback(update, context)
    engine.set_enabled.assert_not_called()
    query.edit_message_text.assert_awaited()
    assert "lecture seule" in query.edit_message_text.await_args.args[0].lower()
