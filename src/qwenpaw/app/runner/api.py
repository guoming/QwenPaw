# -*- coding: utf-8 -*-
"""Chat management API."""
from __future__ import annotations
from typing import Optional
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from agentscope.memory import InMemoryMemory

from .session import SafeJSONSession
from .manager import ChatManager
from .models import (
    ChatSpec,
    ChatUpdate,
    ChatHistory,
)
from .utils import agentscope_msg_to_message


router = APIRouter(prefix="/chats", tags=["chats"])


def _resolve_auth_chat_user_ids(request: Request) -> set[str] | None:
    """Resolve authenticated user ids that may own chats in this request."""
    try:
        from ..deps import get_request_user_id

        auth_user_id = get_request_user_id(request)
        return {auth_user_id, f"console:{auth_user_id}"}
    except HTTPException:
        return None


def _can_access_chat(
    *,
    chat_user_id: str,
    auth_chat_user_ids: set[str] | None,
) -> bool:
    """Allow access only to chats owned by current authenticated user."""
    if auth_chat_user_ids is None:
        return True
    return chat_user_id in auth_chat_user_ids


async def get_workspace(request: Request):
    """Get the workspace for the active agent."""
    from ..agent_context import get_agent_for_request

    return await get_agent_for_request(request)


async def get_chat_manager(
    request: Request,
) -> ChatManager:
    """Get the chat manager for the active agent.

    Args:
        request: FastAPI request object

    Returns:
        ChatManager instance for the specified agent

    Raises:
        HTTPException: If manager is not initialized
    """
    workspace = await get_workspace(request)
    return workspace.chat_manager


async def get_session(
    request: Request,
) -> SafeJSONSession:
    """Get the session for the active agent.

    Args:
        request: FastAPI request object

    Returns:
        SafeJSONSession instance for the specified agent

    Raises:
        HTTPException: If session is not initialized
    """
    workspace = await get_workspace(request)
    return workspace.runner.session


@router.get("", response_model=list[ChatSpec])
async def list_chats(
    request: Request,
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    channel: Optional[str] = Query(None, description="Filter by channel"),
    mgr: ChatManager = Depends(get_chat_manager),
    workspace=Depends(get_workspace),
):
    """List all chats with optional filters.

    Args:
        user_id: Optional user ID to filter chats
        channel: Optional channel name to filter chats
        mgr: Chat manager dependency
    """
    chats = await mgr.list_chats(user_id=user_id, channel=channel)
    auth_chat_user_ids = _resolve_auth_chat_user_ids(request)
    chats = [
        spec
        for spec in chats
        if _can_access_chat(
            chat_user_id=spec.user_id,
            auth_chat_user_ids=auth_chat_user_ids,
        )
    ]
    tracker = workspace.task_tracker
    result = []
    for spec in chats:
        status = await tracker.get_status(spec.id)
        result.append(spec.model_copy(update={"status": status}))
    return result


@router.post("", response_model=ChatSpec)
async def create_chat(
    raw_request: Request,
    request: ChatSpec,
    mgr: ChatManager = Depends(get_chat_manager),
):
    """Create a new chat.

    Server generates chat_id (UUID) automatically.

    Args:
        request: Chat creation request
        mgr: Chat manager dependency

    Returns:
        Created chat spec with UUID
    """
    auth_chat_user_ids = _resolve_auth_chat_user_ids(raw_request)
    if not _can_access_chat(
        chat_user_id=request.user_id,
        auth_chat_user_ids=auth_chat_user_ids,
    ):
        raise HTTPException(status_code=403, detail="Forbidden chat owner")

    chat_id = str(uuid4())
    spec = ChatSpec(
        id=chat_id,
        name=request.name,
        session_id=request.session_id,
        user_id=request.user_id,
        channel=request.channel,
        meta=request.meta,
    )
    return await mgr.create_chat(spec)


@router.post("/batch-delete", response_model=dict)
async def batch_delete_chats(
    request: Request,
    chat_ids: list[str],
    mgr: ChatManager = Depends(get_chat_manager),
):
    """Delete chats by chat IDs.

    Args:
        chat_ids: List of chat IDs
        mgr: Chat manager dependency
    Returns:
        True if deleted, False if failed

    """
    auth_chat_user_ids = _resolve_auth_chat_user_ids(request)
    allowed_chat_ids: list[str] = []
    for chat_id in chat_ids:
        chat_spec = await mgr.get_chat(chat_id)
        if chat_spec is None:
            continue
        if _can_access_chat(
            chat_user_id=chat_spec.user_id,
            auth_chat_user_ids=auth_chat_user_ids,
        ):
            allowed_chat_ids.append(chat_id)
    deleted = await mgr.delete_chats(chat_ids=allowed_chat_ids)
    return {"deleted": deleted}


@router.get("/{chat_id}", response_model=ChatHistory)
async def get_chat(
    request: Request,
    chat_id: str,
    mgr: ChatManager = Depends(get_chat_manager),
    session: SafeJSONSession = Depends(get_session),
    workspace=Depends(get_workspace),
):
    """Get detailed information about a specific chat by UUID.

    Args:
        request: FastAPI request (for agent context)
        chat_id: Chat UUID
        mgr: Chat manager dependency
        session: SafeJSONSession dependency

    Returns:
        ChatHistory with messages and status (idle/running)

    Raises:
        HTTPException: If chat not found (404)
    """
    chat_spec = await mgr.get_chat(chat_id)
    if not chat_spec:
        raise HTTPException(
            status_code=404,
            detail=f"Chat not found: {chat_id}",
        )
    auth_chat_user_ids = _resolve_auth_chat_user_ids(request)
    if not _can_access_chat(
        chat_user_id=chat_spec.user_id,
        auth_chat_user_ids=auth_chat_user_ids,
    ):
        raise HTTPException(status_code=404, detail=f"Chat not found: {chat_id}")

    state = await session.get_session_state_dict(
        chat_spec.session_id,
        chat_spec.user_id,
        chat_spec.channel,
    )
    status = await workspace.task_tracker.get_status(chat_id)
    if not state:
        return ChatHistory(messages=[], status=status)
    memory_state = state.get("agent", {}).get("memory", {})
    memory = InMemoryMemory()
    memory.load_state_dict(memory_state, strict=False)

    memories = await memory.get_memory(prepend_summary=True)
    messages = agentscope_msg_to_message(memories)
    return ChatHistory(messages=messages, status=status)


@router.put("/{chat_id}", response_model=ChatSpec)
async def update_chat(
    request: Request,
    chat_id: str,
    spec: ChatUpdate,
    mgr: ChatManager = Depends(get_chat_manager),
):
    """Update an existing chat.

    Args:
        chat_id: Chat UUID
        spec: Partial chat update payload
        mgr: Chat manager dependency

    Returns:
        Updated chat spec

    Raises:
        HTTPException: If chat not found (404)
    """
    current = await mgr.get_chat(chat_id)
    if current is None:
        raise HTTPException(
            status_code=404,
            detail=f"Chat not found: {chat_id}",
        )
    auth_chat_user_ids = _resolve_auth_chat_user_ids(request)
    if not _can_access_chat(
        chat_user_id=current.user_id,
        auth_chat_user_ids=auth_chat_user_ids,
    ):
        raise HTTPException(status_code=404, detail=f"Chat not found: {chat_id}")

    updated = await mgr.patch_chat(chat_id, spec)
    if updated is None:
        raise HTTPException(
            status_code=404,
            detail=f"Chat not found: {chat_id}",
        )
    return updated


@router.delete("/{chat_id}", response_model=dict)
async def delete_chat(
    request: Request,
    chat_id: str,
    mgr: ChatManager = Depends(get_chat_manager),
):
    """Delete a chat by UUID.

    Note: This only deletes the chat spec (UUID mapping).
    JSONSession state is NOT deleted.

    Args:
        chat_id: Chat UUID
        mgr: Chat manager dependency

    Returns:
        True if deleted, False if failed

    Raises:
        HTTPException: If chat not found (404)
    """
    current = await mgr.get_chat(chat_id)
    if current is None:
        raise HTTPException(
            status_code=404,
            detail=f"Chat not found: {chat_id}",
        )
    auth_chat_user_ids = _resolve_auth_chat_user_ids(request)
    if not _can_access_chat(
        chat_user_id=current.user_id,
        auth_chat_user_ids=auth_chat_user_ids,
    ):
        raise HTTPException(status_code=404, detail=f"Chat not found: {chat_id}")

    deleted = await mgr.delete_chats(chat_ids=[chat_id])
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Chat not found: {chat_id}",
        )
    return {"deleted": True}
