# -*- coding: utf-8 -*-
"""Smoke tests for multi-user authentication and isolation."""
from __future__ import annotations

import httpx

from tests.integration.auth_helpers import auth_headers, register
from tests.integration.conftest import AppServer


def test_unauthenticated_agents_list_returns_401(app_server: AppServer) -> None:
    client = httpx.Client(timeout=app_server.client.timeout, trust_env=False)
    try:
        resp = client.get(f"{app_server.base_url}/api/agents")
        assert resp.status_code == 401
    finally:
        client.close()


def test_non_admin_cannot_create_agent(app_server: AppServer) -> None:
    token_b = register(
        app_server.client,
        app_server.base_url,
        "integ_user_b",
        "integ_user_b_secret",
    )
    resp = app_server.api_request(
        "POST",
        "/api/agents",
        json={
            "id": "integ_forbidden_agent",
            "name": "Forbidden",
            "workspace_dir": "",
        },
        headers=auth_headers(token_b),
    )
    assert resp.status_code == 403, app_server.logs_tail()

