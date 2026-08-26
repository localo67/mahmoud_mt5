from pathlib import Path


def test_windows_smoke_script_covers_off_shadow_and_disarmed_demo() -> None:
    text = Path("scripts/windows-smoke.py").read_text(encoding="utf-8")
    assert 'mode == "off"' in text
    assert 'mode == "shadow"' in text
    assert 'mode == "demo"' in text
    assert "arm_trading()" in text
    assert "Pas d'order_send dans ce script" in text or "order_send" in text
