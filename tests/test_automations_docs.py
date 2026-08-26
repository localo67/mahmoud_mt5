from pathlib import Path


def test_cursor_automations_doc_forbids_order_tools() -> None:
    text = Path("docs/cursor-automations.md").read_text(encoding="utf-8").lower()
    assert "order_send" in text
    assert "secret" in text
    assert "n'executent jamais" in text or "n’executent jamais" in text
