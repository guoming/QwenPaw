# -*- coding: utf-8 -*-
"""Per-user token usage isolation and admin aggregation."""
from __future__ import annotations

from datetime import date

import pytest

from qwenpaw.token_usage.buffer import merge_usage_caches
from qwenpaw.token_usage.manager import TokenUsageManager


@pytest.fixture(autouse=True)
def _isolate_manager():
    TokenUsageManager._instance = None
    yield
    TokenUsageManager._instance = None


class TestMergeUsageCaches:
    def test_merge_sums_counters(self):
        a = {
            "2026-05-01": {
                "p:m": {
                    "provider_id": "p",
                    "model_name": "m",
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "call_count": 1,
                },
            },
        }
        b = {
            "2026-05-01": {
                "p:m": {
                    "provider_id": "p",
                    "model_name": "m",
                    "prompt_tokens": 20,
                    "completion_tokens": 10,
                    "call_count": 2,
                },
            },
        }
        merged = merge_usage_caches([a, b])
        entry = merged["2026-05-01"]["p:m"]
        assert entry["prompt_tokens"] == 30
        assert entry["completion_tokens"] == 15
        assert entry["call_count"] == 3


@pytest.mark.asyncio
class TestTokenUsagePerUser:
    async def test_users_isolated_and_aggregate_all(
        self,
        tmp_path,
        monkeypatch,
    ):
        users_dir = tmp_path / "users"
        users_dir.mkdir()
        monkeypatch.setattr(
            "qwenpaw.token_usage.manager.WORKING_DIR",
            tmp_path,
        )
        monkeypatch.setattr(
            "qwenpaw.token_usage.manager.USERS_DIR",
            users_dir,
        )
        monkeypatch.setattr(
            "qwenpaw.token_usage.manager.TOKEN_USAGE_FILE",
            "token_usage.json",
        )
        monkeypatch.setattr(
            "qwenpaw.constant.USERS_DIR",
            users_dir,
        )

        manager = TokenUsageManager()
        manager.start(flush_interval=1)

        await manager.record(
            provider_id="openai",
            model_name="gpt-4",
            prompt_tokens=100,
            completion_tokens=50,
            user_id="u_alice",
        )
        await manager.record(
            provider_id="openai",
            model_name="gpt-4",
            prompt_tokens=200,
            completion_tokens=100,
            user_id="u_bob",
        )

        alice = await manager.get_summary(
            start_date=date(2026, 5, 1),
            end_date=date.today(),
            user_id="u_alice",
        )
        bob = await manager.get_summary(
            start_date=date(2026, 5, 1),
            end_date=date.today(),
            user_id="u_bob",
        )
        all_users = await manager.get_summary(
            start_date=date(2026, 5, 1),
            end_date=date.today(),
            aggregate_all=True,
        )

        assert alice.total_prompt_tokens == 100
        assert bob.total_prompt_tokens == 200
        assert all_users.total_prompt_tokens == 300
        assert all_users.total_calls == 2

        await manager.stop()
