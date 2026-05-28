# -*- coding: utf-8 -*-
"""Tests for always-on auth and is_admin."""
import json

import pytest

from qwenpaw.app.auth import (
    authenticate,
    is_auth_enabled,
    register_user,
    verify_token,
    verify_token_payload,
)


@pytest.fixture
def auth_paths(tmp_path, monkeypatch):
    monkeypatch.setattr("qwenpaw.app.auth.AUTH_FILE", tmp_path / "auth.json")
    monkeypatch.setattr("qwenpaw.app.auth.SECRET_DIR", tmp_path)
    return tmp_path


def test_auth_always_enabled(auth_paths):
    assert is_auth_enabled() is True


def test_first_user_is_admin(auth_paths):
    token = register_user("admin", "secret123")
    assert token is not None
    data = json.loads((auth_paths / "auth.json").read_text())
    users = data["users"]
    assert len(users) == 1
    assert users[0]["is_admin"] is True
    assert users[0]["user_id"].startswith("u_")

    payload = verify_token_payload(token)
    assert payload is not None
    assert payload["is_admin"] is True
    assert payload["user_id"] == users[0]["user_id"]
    assert verify_token(token) == "admin"


def test_second_user_not_admin(auth_paths):
    register_user("admin", "secret123")
    token = register_user("bob", "secret456")
    assert token is not None
    data = json.loads((auth_paths / "auth.json").read_text())
    admins = [u for u in data["users"] if u.get("is_admin")]
    assert len(admins) == 1
    assert admins[0]["username"] == "admin"

    payload = verify_token_payload(token)
    assert payload is not None
    assert payload["is_admin"] is False
    assert payload["sub"] == "bob"


def test_authenticate_returns_admin_flag(auth_paths):
    register_user("admin", "secret123")
    token = authenticate("admin", "secret123")
    assert verify_token_payload(token)["is_admin"] is True
