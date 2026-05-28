# -*- coding: utf-8 -*-
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from qwenpaw.app.deps import (
    get_request_user_id,
    is_request_admin,
    require_admin,
    resolve_stats_scope,
)


def _req(**state):
    scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    req = Request(scope)
    for key, value in state.items():
        setattr(req.state, key, value)
    return req


def test_get_request_user_id_missing():
    with pytest.raises(HTTPException) as exc:
        get_request_user_id(_req())
    assert exc.value.status_code == 401


def test_get_request_user_id_ok():
    assert get_request_user_id(_req(user_id="u_abc")) == "u_abc"


def test_require_admin_forbidden():
    with pytest.raises(HTTPException) as exc:
        require_admin(_req(user_id="u1", is_admin=False))
    assert exc.value.status_code == 403


def test_require_admin_ok():
    require_admin(_req(user_id="u1", is_admin=True))


def test_is_request_admin_from_auth_file(monkeypatch):
    monkeypatch.setattr(
        "qwenpaw.app.deps._load_auth_data",
        lambda: {
            "users": [
                {
                    "user_id": "u_admin",
                    "username": "admin",
                    "is_admin": True,
                },
            ],
        },
    )
    assert is_request_admin(_req(user_id="u_admin", is_admin=False)) is True


def test_resolve_stats_scope_all_requires_admin():
    with pytest.raises(HTTPException) as exc:
        resolve_stats_scope(_req(user_id="u1", is_admin=False), "all")
    assert exc.value.status_code == 403


def test_resolve_stats_scope_all_ok_for_admin():
    uid, aggregate = resolve_stats_scope(
        _req(user_id="u1", is_admin=True),
        "all",
    )
    assert uid == "u1"
    assert aggregate is True
