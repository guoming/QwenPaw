# -*- coding: utf-8 -*-
"""Unit tests for chat API ownership isolation helpers."""

from qwenpaw.app.runner.api import _can_access_chat


def test_non_admin_cannot_access_other_console_chat() -> None:
    assert not _can_access_chat(
        chat_user_id="console:user_b",
        auth_chat_user_ids={"user_a", "console:user_a"},
    )


def test_non_admin_can_access_own_console_chat() -> None:
    assert _can_access_chat(
        chat_user_id="console:user_a",
        auth_chat_user_ids={"user_a", "console:user_a"},
    )


def test_non_admin_cannot_access_foreign_non_console_chat() -> None:
    assert not _can_access_chat(
        chat_user_id="dingtalk:external-user",
        auth_chat_user_ids={"user_a", "console:user_a"},
    )


def test_non_admin_can_access_own_legacy_user_id_chat() -> None:
    assert _can_access_chat(
        chat_user_id="user_a",
        auth_chat_user_ids={"user_a", "console:user_a"},
    )


def test_unscoped_access_without_auth_context() -> None:
    assert _can_access_chat(
        chat_user_id="console:user_b",
        auth_chat_user_ids=None,
    )
