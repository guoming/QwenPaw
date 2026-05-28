# -*- coding: utf-8 -*-
"""In-memory store for console channel push messages (e.g. cron text).

Messages are scoped by ``auth_user_id`` when set so users do not see each
other's push notifications.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Dict, List

_list: List[Dict[str, Any]] = []
_lock = asyncio.Lock()
_MAX_AGE_SECONDS = 60
_MAX_MESSAGES = 500


async def append(
    session_id: str,
    text: str,
    *,
    sticky: bool = False,
    auth_user_id: str | None = None,
) -> None:
    """Append a message (bounded: oldest dropped if over _MAX_MESSAGES)."""
    if not session_id or not text:
        return
    async with _lock:
        _list.append(
            {
                "id": str(uuid.uuid4()),
                "text": text,
                "sticky": sticky,
                "ts": time.time(),
                "session_id": session_id,
                "auth_user_id": auth_user_id or "",
            },
        )
        if len(_list) > _MAX_MESSAGES:
            _list.sort(key=lambda m: m["ts"])
            del _list[: len(_list) - _MAX_MESSAGES]


def _matches_user(msg: dict[str, Any], auth_user_id: str | None) -> bool:
    if not auth_user_id:
        return True
    stored = msg.get("auth_user_id") or ""
    if not stored:
        return True
    return stored == auth_user_id


async def take(
    session_id: str,
    auth_user_id: str | None = None,
) -> List[Dict[str, Any]]:
    """Return and remove messages for the session (optionally filtered by user)."""
    if not session_id:
        return []
    async with _lock:
        _prune_expired_locked(_MAX_AGE_SECONDS)
        out = []
        remaining = []
        for msg in _list:
            if msg.get("session_id") == session_id and _matches_user(
                msg,
                auth_user_id,
            ):
                out.append(msg)
            else:
                remaining.append(msg)
        _list[:] = remaining
        return _strip_ts(out)


async def take_all(auth_user_id: str | None = None) -> List[Dict[str, Any]]:
    """Return and remove all non-expired messages for a user."""
    async with _lock:
        _prune_expired_locked(_MAX_AGE_SECONDS)
        out = [m for m in _list if _matches_user(m, auth_user_id)]
        _list[:] = [m for m in _list if not _matches_user(m, auth_user_id)]
        return _strip_ts(out)


def _strip_ts(msgs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "id": m["id"],
            "text": m["text"],
            "sticky": bool(m.get("sticky", False)),
        }
        for m in msgs
    ]


def _prune_expired_locked(max_age_seconds: int) -> None:
    cutoff = time.time() - max_age_seconds
    _list[:] = [m for m in _list if m["ts"] >= cutoff]


async def get_recent(
    max_age_seconds: int = _MAX_AGE_SECONDS,
    auth_user_id: str | None = None,
) -> List[Dict[str, Any]]:
    """Return recent messages without consuming them."""
    if max_age_seconds < 0:
        raise ValueError("max_age_seconds must be non-negative")

    async with _lock:
        _prune_expired_locked(max_age_seconds)
        filtered = [m for m in _list if _matches_user(m, auth_user_id)]
        return _strip_ts(filtered)
