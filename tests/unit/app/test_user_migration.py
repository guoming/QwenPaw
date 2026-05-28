# -*- coding: utf-8 -*-
import json

from qwenpaw import constant
from qwenpaw.app import user_migration
from qwenpaw.app.auth import register_user


def test_migrate_legacy_inbox_to_admin(tmp_path, monkeypatch):
    monkeypatch.setattr(constant, "WORKING_DIR", tmp_path)
    monkeypatch.setattr(constant, "USERS_DIR", tmp_path / "users")
    monkeypatch.setattr("qwenpaw.app.auth.AUTH_FILE", tmp_path / "auth.json")
    monkeypatch.setattr("qwenpaw.app.auth.SECRET_DIR", tmp_path)

    (tmp_path / "inbox_events.json").write_text(
        json.dumps([{"id": "e1", "title": "legacy"}]),
        encoding="utf-8",
    )

    register_user("admin", "secret123")
    assert user_migration.migrate_legacy_to_admin_user() is True
    assert user_migration.migration_completed() is True

    users = list((tmp_path / "users").iterdir())
    assert len(users) == 1
    migrated = users[0] / "inbox_events.json"
    assert migrated.is_file()
    events = json.loads(migrated.read_text(encoding="utf-8"))
    assert events[0]["id"] == "e1"
