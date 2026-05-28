# -*- coding: utf-8 -*-
"""Token usage API for console and skill tool."""

from datetime import date, timedelta

from fastapi import APIRouter, Query, Request

from ...token_usage import (
    get_token_usage_manager,
    TokenUsageSummary,
    TokenUsageRecord,
)
from ..deps import resolve_stats_scope

router = APIRouter(prefix="/token-usage", tags=["token-usage"])


def _parse_date(s: str | None) -> date | None:
    """Parse YYYY-MM-DD string to date."""
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


@router.get(
    "",
    summary="Get token usage summary",
    description="Return aggregated token usage by date, model, and provider",
)
async def get_token_usage(
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
    model: str
    | None = Query(
        None,
        description="Filter by model name",
    ),
    provider: str
    | None = Query(
        None,
        description="Filter by provider ID",
    ),
    scope: str
    | None = Query(
        None,
        description="Use scope=all (admin only) to aggregate all users",
    ),
) -> TokenUsageSummary:
    """Return aggregated token usage summary for the given date range."""
    end_d = _parse_date(end_date) or date.today()
    start_d = _parse_date(start_date) or (end_d - timedelta(days=30))
    if start_d > end_d:
        start_d, end_d = end_d, start_d

    user_id, aggregate_all = resolve_stats_scope(request, scope)

    return await get_token_usage_manager().get_summary(
        start_date=start_d,
        end_date=end_d,
        model_name=model,
        provider_id=provider,
        user_id=None if aggregate_all else user_id,
        aggregate_all=aggregate_all,
    )


@router.get(
    "/details",
    summary="Get token usage details",
    description="Return raw token usage records for frontend aggregation",
)
async def get_token_usage_details(
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
    model: str
    | None = Query(
        None,
        description="Filter by model name",
    ),
    provider: str
    | None = Query(
        None,
        description="Filter by provider ID",
    ),
    scope: str
    | None = Query(
        None,
        description="Use scope=all (admin only) to aggregate all users",
    ),
) -> list[TokenUsageRecord]:
    """Return raw token usage records for the given date range."""
    end_d = _parse_date(end_date) or date.today()
    start_d = _parse_date(start_date) or (end_d - timedelta(days=30))
    if start_d > end_d:
        start_d, end_d = end_d, start_d

    user_id, aggregate_all = resolve_stats_scope(request, scope)

    return await get_token_usage_manager().get_details(
        start_date=start_d,
        end_date=end_d,
        model_name=model,
        provider_id=provider,
        user_id=None if aggregate_all else user_id,
        aggregate_all=aggregate_all,
    )
