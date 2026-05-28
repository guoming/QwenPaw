# -*- coding: utf-8 -*-
import asyncio

from qwenpaw import constant
from qwenpaw.app.inbox_store import append_event, list_events


def test_inbox_per_user_isolation(tmp_path, monkeypatch):
    monkeypatch.setattr(constant, "USERS_DIR", tmp_path / "users")
    monkeypatch.setattr(constant, "WORKING_DIR", tmp_path)

    async def _run() -> None:
        await append_event(
            agent_id="default",
            source_type="test",
            source_id="a",
            event_type="notice",
            status="unread",
            title="for user a",
            body="a",
            user_id="user_a",
        )
        await append_event(
            agent_id="default",
            source_type="test",
            source_id="b",
            event_type="notice",
            status="unread",
            title="for user b",
            body="b",
            user_id="user_b",
        )

        events_a = await list_events(user_id="user_a")
        events_b = await list_events(user_id="user_b")

        titles_a = {e["title"] for e in events_a}
        titles_b = {e["title"] for e in events_b}
        assert "for user a" in titles_a
        assert "for user b" not in titles_a
        assert "for user b" in titles_b
        assert "for user a" not in titles_b

    asyncio.run(_run())
