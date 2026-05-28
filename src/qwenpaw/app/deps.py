# -*- coding: utf-8 -*-
"""FastAPI request dependencies for auth and admin checks."""
from __future__ import annotations

from fastapi import HTTPException, Request

from .auth import _find_user_by_username, _get_users, _load_auth_data


def get_request_user_id(request: Request) -> str:
    """Return the authenticated user's ID from request state."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id


def is_request_admin(request: Request) -> bool:
    """Return whether the authenticated user is an administrator.

    Uses JWT ``is_admin`` when present, and falls back to ``auth.json`` so
    tokens issued before multi-user support still work for admin users.
    """
    if getattr(request.state, "is_admin", False):
        return True

    user_id = getattr(request.state, "user_id", None)
    if user_id:
        data = _load_auth_data()
        if not data.get("_auth_load_error"):
            for user in _get_users(data):
                if user.get("user_id") == user_id:
                    return bool(user.get("is_admin", False))

    username = getattr(request.state, "user", None)
    if username:
        record = _find_user_by_username(username)
        if record:
            return bool(record.get("is_admin", False))

    return False


def require_admin(request: Request) -> None:
    """Raise 403 unless the caller is an administrator."""
    if not is_request_admin(request):
        raise HTTPException(status_code=403, detail="Admin only")


def resolve_stats_scope(
    request: Request,
    scope: str | None,
) -> tuple[str, bool]:
    """Return ``(user_id, aggregate_all)`` for usage / agent statistics APIs.

  * Normal users always get their own ``user_id`` and ``aggregate_all=False``.
  * Admins may pass ``scope=all`` to aggregate across all users.
    """
    user_id = get_request_user_id(request)
    if scope == "all":
        if not is_request_admin(request):
            raise HTTPException(
                status_code=403,
                detail="Admin only",
            )
        return user_id, True
    return user_id, False
