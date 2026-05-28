# -*- coding: utf-8 -*-
"""Agent statistics API for console."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Query, Request

from ...agent_stats import AgentStatsSummary, get_agent_stats_service
from ..agent_context import get_agent_for_request
from ..deps import resolve_stats_scope
from ..user_agent_registry import list_user_agent_workspace_dirs

router = APIRouter(prefix="/agent-stats", tags=["agent-stats"])


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


@router.get(
    "",
    summary="Get agent statistics summary",
    description="Return comprehensive agent statistics for the date range",
)
async def get_agent_statistics(
    request: Request,
    start_date: str
    | None = Query(
        None,
        description="Start date YYYY-MM-DD (inclusive). Default: 30 days ago",
    ),
    end_date: str
    | None = Query(
        None,
        description="End date YYYY-MM-DD (inclusive). Default: today",
    ),
    scope: str
    | None = Query(
        None,
        description="Use scope=all (admin only) to aggregate all users",
    ),
) -> AgentStatsSummary:
    end_d = _parse_date(end_date) or date.today()
    start_d = _parse_date(start_date) or (end_d - timedelta(days=30))
    if start_d > end_d:
        start_d, end_d = end_d, start_d

    workspace = await get_agent_for_request(request)
    user_id, aggregate_all = resolve_stats_scope(request, scope)

    if aggregate_all:
        workspace_dirs = list_user_agent_workspace_dirs(workspace.agent_id)
        if not workspace_dirs:
            workspace_dirs = [workspace.workspace_dir]
    else:
        workspace_dirs = [workspace.workspace_dir]

    service = get_agent_stats_service()
    return await service.get_summary(
        workspace_dirs=workspace_dirs,
        start_date=start_d,
        end_date=end_d,
        user_id=user_id,
        aggregate_all_tokens=aggregate_all,
    )
