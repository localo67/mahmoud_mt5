import os
import subprocess
import sys
from pathlib import Path

import pytest

import config


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_trading_mode(value: str | None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if value is None:
        env.pop("TRADING_MODE", None)
    else:
        env["TRADING_MODE"] = value
    return subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import dotenv; "
                "dotenv.load_dotenv = lambda: None; "
                "import config; "
                "print(config.TRADING_MODE)"
            ),
        ],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_trading_mode_defaults_to_off() -> None:
    result = _load_trading_mode(None)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "off"


@pytest.mark.parametrize("mode", ["off", "shadow", "demo", "live"])
def test_trading_mode_recognizes_only_documented_modes(mode: str) -> None:
    result = _load_trading_mode(mode.upper())

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == mode


def test_invalid_trading_mode_is_rejected() -> None:
    result = _load_trading_mode("paper")

    assert result.returncode != 0
    assert "TRADING_MODE invalide" in result.stderr


def _set_valid_non_mt5_config(
    monkeypatch: pytest.MonkeyPatch,
    trading_mode: str,
) -> None:
    monkeypatch.setattr(config, "TELEGRAM_TOKEN", "telegram-token")
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "openrouter-key")
    monkeypatch.setattr(config, "AUTHORIZED_CHAT_ID", 123)
    monkeypatch.setattr(config, "TRADING_MODE", trading_mode)
    monkeypatch.setattr(config, "MT5_LOGIN", 0)
    monkeypatch.setattr(config, "MT5_PASSWORD", "")
    monkeypatch.setattr(config, "MT5_SERVER", "")


def test_off_mode_does_not_require_mt5_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_valid_non_mt5_config(monkeypatch, "off")

    assert config.validate_config() is True


@pytest.mark.parametrize("mode", ["shadow", "demo", "live"])
def test_mt5_modes_require_mt5_credentials(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    _set_valid_non_mt5_config(monkeypatch, mode)

    assert config.validate_config() is False
