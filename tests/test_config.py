import os
import subprocess
import sys
from pathlib import Path

import pytest


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
