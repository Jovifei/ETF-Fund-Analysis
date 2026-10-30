"""Test SMTP config update/overwrite and NotificationQueue auto-prune on capacity limit."""
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import pytest

from app.workspace.local_notifications import (
    NotificationQueue, SMTPConfig, save_smtp_config, load_smtp_config, MAX_ITEMS
)


def test_smtp_config_allow_overwrite(tmp_path):
    # Only runs on Windows where DPAPI is available
    if os.name != "nt":
        pytest.skip("Windows DPAPI required")

    (tmp_path / ".local-live").write_text("live", encoding="utf-8")
    cfg = SMTPConfig(
        host="smtp.example.com",
        port=465,
        mode="ssl",
        username="user@example.com",
        password="secret_password",
        sender="user@example.com",
        recipient="user@example.com"
    )
    
    # First save with enabled=False
    path = save_smtp_config(tmp_path, cfg, enabled=False, owner_confirmed=False)
    assert path.is_file()

    # Second save without overwrite must raise ValueError
    with pytest.raises(ValueError, match="already exists"):
        save_smtp_config(tmp_path, cfg, enabled=False, owner_confirmed=False, overwrite=False)

    # Second save WITH overwrite=True must succeed
    path2 = save_smtp_config(tmp_path, cfg, enabled=True, owner_confirmed=True, overwrite=True)
    assert path2 == path
    
    loaded, policy = load_smtp_config(tmp_path)
    assert policy["enabled"] is True
    assert policy["owner_confirmed"] is True


def test_notification_queue_prunes_old_terminal_on_capacity(tmp_path):
    queue = NotificationQueue(tmp_path)
    now = datetime(2026, 10, 30, 15, 0, tzinfo=timezone.utc)
    recipient_id = "0" * 64

    # Enqueue a baseline message
    binding = {
        "session": "2026-10-30",
        "slot": "14:30",
        "kind": "normal",
        "generation": 1,
        "bundle_id": "a" * 64,
        "recipient_id": recipient_id
    }
    eid = queue.enqueue(subject="Test 1", body="Body 1", binding=binding, now=now)
    assert eid is not None

    # Simulate db having MAX_ITEMS messages where many are old ACCEPTED messages
    with queue._transaction() as db:
        old_time = (now - timedelta(days=40)).isoformat()
        # Insert dummy accepted messages up to MAX_ITEMS
        for i in range(MAX_ITEMS - 1):
            db.execute(
                "INSERT INTO messages(id, event_key, payload_hash, subject, body, binding, state, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'ACCEPTED', ?)",
                (f"dummy_{i}", f"ek_{i}", f"ph_{i}", "sub", "body", json.dumps(binding), old_time)
            )
        count = db.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        assert count == MAX_ITEMS

    # Now enqueue a new slot message. With our fix, it should automatically prune old ACCEPTED messages and succeed!
    new_binding = {
        "session": "2026-10-30",
        "slot": "14:45",
        "kind": "normal",
        "generation": 2,
        "bundle_id": "b" * 64,
        "recipient_id": recipient_id
    }
    new_eid = queue.enqueue(subject="Test 2", body="Body 2", binding=new_binding, now=now)
    assert new_eid is not None
