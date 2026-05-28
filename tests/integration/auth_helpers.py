# -*- coding: utf-8 -*-
"""Helpers for authenticated integration tests."""
from __future__ import annotations

from typing import Any

import httpx

INTEG_TEST_ADMIN_USER = "integ_admin"
INTEG_TEST_ADMIN_PASSWORD = "integ_test_secret_12345"


def login(
    client: httpx.Client,
    base_url: str,
    username: str,
    password: str,
) -> str:
    """Return a bearer token for ``username`` / ``password``."""
    resp = client.post(
        f"{base_url}/api/auth/login",
        json={"username": username, "password": password},
    )
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()
    return str(data["token"])


def register(
    client: httpx.Client,
    base_url: str,
    username: str,
    password: str,
) -> str:
    """Register a user and return bearer token."""
    resp = client.post(
        f"{base_url}/api/auth/register",
        json={"username": username, "password": password},
    )
    resp.raise_for_status()
    return str(resp.json()["token"])


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
