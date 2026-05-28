# -*- coding: utf-8 -*-
"""Middleware: require admin for global Settings write APIs."""
from __future__ import annotations

import json

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .deps import require_admin

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def path_requires_admin_write(path: str, method: str) -> bool:
    """Return True when the request mutates global Settings resources."""
    if method not in _WRITE_METHODS:
        return False

    if path.startswith("/api/agents/"):
        suffix = path[len("/api/agents/") :]
        if not suffix:
            return True
        first = suffix.split("/")[0]
        if first == "from-template":
            return False
        parts = suffix.rstrip("/").split("/")
        if len(parts) == 2 and parts[1] == "self":
            return False
        if first == "order":
            return True
        if "/" not in suffix.rstrip("/"):
            return True
        return False

    if path == "/api/agents":
        return True

    admin_prefixes = (
        "/api/models",
        "/api/local-models",
        "/api/envs",
        "/api/backups",
        "/api/plugins",
        "/api/config/security",
        "/api/market",
        "/api/workspace/transcription",
    )
    if any(path.startswith(prefix) for prefix in admin_prefixes):
        return True

    if path.startswith("/api/skills/pool"):
        return method != "GET"

    return False


class AdminWriteMiddleware(BaseHTTPMiddleware):
    """Reject non-admin users mutating global Settings."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if path_requires_admin_write(request.url.path, request.method):
            try:
                require_admin(request)
            except HTTPException as exc:
                return Response(
                    content=json.dumps({"detail": exc.detail}),
                    status_code=exc.status_code,
                    media_type="application/json",
                )
        return await call_next(request)
