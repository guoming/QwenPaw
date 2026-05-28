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


def test_non_admin_can_read_agents_list(app_server: AppServer) -> None:
    token_b = register(
        app_server.client,
        app_server.base_url,
        "integ_user_list_only",
        "integ_user_list_only_secret",
    )
    resp = app_server.api_request(
        "GET",
        "/api/agents",
        headers=auth_headers(token_b),
    )
    assert resp.status_code == 200, app_server.logs_tail()
    assert isinstance(resp.json().get("agents"), list)


def test_new_user_agents_list_is_empty_before_self_provision(
    app_server: AppServer,
) -> None:
    token = register(
        app_server.client,
        app_server.base_url,
        "integ_user_empty_list",
        "integ_user_empty_list_secret",
    )
    resp = app_server.api_request(
        "GET",
        "/api/agents",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, app_server.logs_tail()
    assert resp.json().get("agents") == []


def test_non_admin_cannot_toggle_agent(app_server: AppServer) -> None:
    token_b = register(
        app_server.client,
        app_server.base_url,
        "integ_user_toggle_forbidden",
        "integ_user_toggle_forbidden_secret",
    )
    resp = app_server.api_request(
        "PATCH",
        "/api/agents/default/toggle",
        json={"enabled": False},
        headers=auth_headers(token_b),
    )
    assert resp.status_code == 403, app_server.logs_tail()

