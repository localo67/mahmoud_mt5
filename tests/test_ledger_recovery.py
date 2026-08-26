import sqlite3

from core.ledger import Ledger


def test_ledger_rejects_update_and_delete(tmp_path) -> None:
    ledger = Ledger(tmp_path / "ledger.sqlite")
    ledger.append("dec-1", "intent", {"symbol": "XAUUSD"})
    try:
        ledger._conn.execute("UPDATE events SET kind='x' WHERE decision_id='dec-1'")
        raise AssertionError("update must be rejected")
    except sqlite3.Error as exc:
        assert "append-only" in str(exc)
    try:
        ledger._conn.execute("DELETE FROM events WHERE decision_id='dec-1'")
        raise AssertionError("delete must be rejected")
    except sqlite3.Error as exc:
        assert "append-only" in str(exc)


def test_duplicate_event_id_is_ignored(tmp_path) -> None:
    ledger = Ledger(tmp_path / "ledger.sqlite")
    first = ledger.append("dec-1", "intent", {"symbol": "XAUUSD"}, event_id="same")
    second = ledger.append("dec-1", "intent", {"symbol": "XAUUSD"}, event_id="same")
    assert first is True
    assert second is False
    assert len(ledger.events("dec-1")) == 1


def test_backup_integrity_and_restore(tmp_path) -> None:
    source_path = tmp_path / "ledger.sqlite"
    ledger = Ledger(source_path)
    ledger.append("dec-1", "intent", {"symbol": "XAUUSD"})
    ledger.append("dec-1", "fill_final", {"volume": 0.01})
    backup = ledger.backup(tmp_path / "backup.sqlite")
    assert backup["ok"] is True
    assert backup["sha256"]
    restored_path = tmp_path / "restored.sqlite"
    restored = ledger.restore_to(tmp_path / "backup.sqlite", restored_path)
    assert restored["ok"] is True
    assert restored["armed"] is False
    copy = Ledger(restored_path)
    assert len(copy.events("dec-1")) == 2
    copy.close()
    ledger.close()
