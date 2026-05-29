# -*- coding: utf-8 -*-
"""Integration tests for self-provisioning agents from templates."""

from __future__ import annotations

from tests.integration.auth_helpers import auth_headers, register
from tests.integration.conftest import AppServer


def test_non_admin_can_list_enabled_agent_templates(app_server: AppServer) -> None:
    token = register(
        app_server.client,
        app_server.base_url,
        "integ_user_template_list",
        "integ_user_template_list_secret",
    )
    resp = app_server.api_request(
        "GET",
        "/api/agent-templates",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, app_server.logs_tail()
    templates = resp.json()["templates"]
    assert isinstance(templates, list)
    assert all(t["enabled"] is True for t in templates)


def test_non_admin_can_create_private_agent_from_template(
    app_server: AppServer,
) -> None:
    token = register(
        app_server.client,
        app_server.base_url,
        "integ_user_template_create",
        "integ_user_template_create_secret",
    )
    create_resp = app_server.api_request(
        "POST",
        "/api/agents/from-template",
        json={
            "template_agent_id": "default",
            "name": "My Private Agent",
            "description": "created from template",
        },
        headers=auth_headers(token),
    )
    assert create_resp.status_code == 201, app_server.logs_tail()
    created_id = create_resp.json()["id"]
    assert created_id == "default"

    list_resp = app_server.api_request(
        "GET",
        "/api/agents",
        headers=auth_headers(token),
    )
    ids = [a["id"] for a in list_resp.json()["agents"]]
    assert created_id in ids


def test_same_template_cannot_provision_twice(
    app_server: AppServer,
) -> None:
    token = register(
        app_server.client,
        app_server.base_url,
        "integ_user_template_multi",
        "integ_user_template_multi_secret",
    )
    first = app_server.api_request(
        "POST",
        "/api/agents/from-template",
        json={"template_agent_id": "default", "name": "First"},
        headers=auth_headers(token),
    )
    second = app_server.api_request(
        "POST",
        "/api/agents/from-template",
        json={"template_agent_id": "default", "name": "Second"},
        headers=auth_headers(token),
    )
    assert first.status_code == 201, app_server.logs_tail()
    assert second.status_code == 409, app_server.logs_tail()
    assert first.json()["id"] == "default"
    assert "already exists" in second.json()["detail"].lower()


def test_private_agent_agent_scoped_status(app_server: AppServer) -> None:
    token = register(
        app_server.client,
        app_server.base_url,
        "integ_user_template_status",
        "integ_user_template_status_secret",
    )
    headers = auth_headers(token)
    create_resp = app_server.api_request(
        "POST",
        "/api/agents/from-template",
        json={"template_agent_id": "default"},
        headers=headers,
    )
    assert create_resp.status_code == 201, app_server.logs_tail()
    private_id = create_resp.json()["id"]

    status_resp = app_server.api_request(
        "GET",
        f"/api/agents/{private_id}/agent-status",
        headers=headers,
    )
    assert status_resp.status_code == 200, app_server.logs_tail()
    body = status_resp.json()
    assert body.get("status") in {"idle", "running", "disabled"}


def test_user_can_update_and_delete_private_agent(app_server: AppServer) -> None:
    token = register(
        app_server.client,
        app_server.base_url,
        "integ_user_template_crud",
        "integ_user_template_crud_secret",
    )
    headers = auth_headers(token)
    create_resp = app_server.api_request(
        "POST",
        "/api/agents/from-template",
        json={"template_agent_id": "default", "name": "Before"},
        headers=headers,
    )
    assert create_resp.status_code == 201, app_server.logs_tail()
    private_id = create_resp.json()["id"]

    patch_resp = app_server.api_request(
        "PATCH",
        f"/api/agents/{private_id}/self",
        json={"name": "After", "description": "updated"},
        headers=headers,
    )
    assert patch_resp.status_code == 200, app_server.logs_tail()
    assert patch_resp.json()["name"] == "After"

    delete_resp = app_server.api_request(
        "DELETE",
        f"/api/agents/{private_id}/self",
        headers=headers,
    )
    assert delete_resp.status_code == 200, app_server.logs_tail()

    list_resp = app_server.api_request(
        "GET",
        "/api/agents",
        headers=headers,
    )
    ids = [a["id"] for a in list_resp.json()["agents"]]
    assert private_id not in ids
