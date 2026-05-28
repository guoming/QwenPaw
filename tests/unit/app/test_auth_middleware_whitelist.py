# -*- coding: utf-8 -*-
"""Auth middleware should still attach user state from Bearer on IP whitelist."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from starlette.requests import Request
from starlette.responses import Response

from qwenpaw.app.auth import AuthMiddleware, create_token, register_user


@pytest.mark.asyncio
async def test_whitelist_skip_still_attaches_user_from_token(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("qwenpaw.app.auth.AUTH_FILE", tmp_path / "auth.json")
    monkeypatch.setattr("qwenpaw.app.auth.SECRET_DIR", tmp_path)

    token = register_user("alice", "secret-pass")
    assert token

    async def call_next(request: Request) -> Response:
        assert getattr(request.state, "user_id", None)
        assert request.state.user == "alice"
        return Response("ok")

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/chats",
        "headers": [(b"authorization", f"Bearer {token}".encode())],
        "client": ("127.0.0.1", 64013),
        "server": ("127.0.0.1", 8088),
    }
    request = Request(scope)

    middleware = AuthMiddleware(app=None)
    with patch.object(middleware, "_should_skip_auth", return_value=True):
        response = await middleware.dispatch(request, call_next)

    assert response.status_code == 200
