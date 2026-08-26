from pathlib import Path


def test_windows_smoke_script_covers_off_shadow_and_disarmed_demo() -> None:
    text = Path("scripts/windows-smoke.py").read_text(encoding="utf-8")
    assert 'mode == "off"' in text
    assert 'mode == "shadow"' in text
    assert 'mode == "demo"' in text
    assert "arm_trading()" in text
    assert "Pas d'order_send dans ce script" in text or "order_send" in text


def test_windows_run_scripts_exist() -> None:
    root = Path("scripts/windows")
    for name in (
        "00-setup.ps1",
        "01-test-connexion.ps1",
        "run-scalp-eurusd.ps1",
        "run-scalp-xauusd.ps1",
        "run-breakout-xauusd.ps1",
    ):
        assert (root / name).is_file()
    runner = (root / "_run-pack.ps1").read_text(encoding="utf-8")
    assert "--headless" in runner
    assert "--arm-demo" in runner
    assert "TRADING_MODE" in runner
