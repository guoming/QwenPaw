# -*- coding: utf-8 -*-
"""Token usage manager — thin orchestrator.
"""

import logging
import threading
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from ..constant import (
    TOKEN_USAGE_FILE,
    USERS_DIR,
    WORKING_DIR,
    user_token_usage_path,
)
from .buffer import TokenUsageBuffer, _UsageEvent, merge_usage_caches

logger = logging.getLogger(__name__)

_LEGACY_KEY = "__legacy__"


class TokenUsageStats(BaseModel):
    """Prompt/completion tokens and call count."""

    prompt_tokens: int = Field(0, ge=0)
    completion_tokens: int = Field(0, ge=0)
    call_count: int = Field(0, ge=0)


class TokenUsageRecord(TokenUsageStats):
    """Single row from token usage query (per date + provider + model)."""

    date: str = Field(..., description="Date (YYYY-MM-DD)")
    provider_id: str = Field("", description="Provider ID")
    model: str = Field(..., description="Model name")


class TokenUsageByModel(TokenUsageStats):
    """Per-model aggregate in summary (provider + model + counts)."""

    provider_id: str = Field("", description="Provider ID")
    model: str = Field(..., description="Model name")


class TokenUsageByDateModel(TokenUsageStats):
    """Per-date per-model aggregate in summary."""

    provider_id: str = Field("", description="Provider ID")
    model: str = Field(..., description="Model name")


class TokenUsageSummary(BaseModel):
    """Aggregated token usage summary returned by get_summary()."""

    total_prompt_tokens: int = Field(0, ge=0)
    total_completion_tokens: int = Field(0, ge=0)
    total_calls: int = Field(0, ge=0)
    by_model: dict[str, TokenUsageByModel] = Field(
        default_factory=dict,
        description="Per model (provider:model key) aggregation",
    )
    by_date: dict[str, TokenUsageStats] = Field(
        default_factory=dict,
        description="Per date (YYYY-MM-DD) - all models combined",
    )


class TokenUsageManager:
    """Orchestrator for token usage recording and querying."""

    _instance: "TokenUsageManager | None" = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._buffers: dict[str, TokenUsageBuffer] = {}
        self._buffers_lock = threading.Lock()
        self._flush_interval = 10
        self._started = False

    def _path_for_key(self, cache_key: str) -> Path:
        if cache_key == _LEGACY_KEY:
            return (WORKING_DIR / TOKEN_USAGE_FILE).expanduser()
        return user_token_usage_path(cache_key)

    def _buffer_for_key(self, cache_key: str) -> TokenUsageBuffer:
        with self._buffers_lock:
            buf = self._buffers.get(cache_key)
            if buf is None:
                path = self._path_for_key(cache_key)
                if cache_key != _LEGACY_KEY:
                    path.parent.mkdir(parents=True, exist_ok=True)
                buf = TokenUsageBuffer(
                    path,
                    flush_interval=self._flush_interval,
                )
                self._buffers[cache_key] = buf
                if self._started:
                    buf.start()
            return buf

    def _resolve_record_key(self, user_id: str | None) -> str:
        if user_id:
            return user_id
        from ..config.context import get_current_user_id

        ctx_uid = get_current_user_id()
        if ctx_uid:
            return ctx_uid
        return _LEGACY_KEY

    def start(self, flush_interval: int = 10) -> None:
        """Start background flush tasks for active buffers."""
        self._flush_interval = flush_interval
        self._started = True
        with self._buffers_lock:
            for buf in self._buffers.values():
                if buf._consumer_task is None:
                    buf._flush_interval = flush_interval
                    buf.start()

    async def stop(self) -> None:
        """Stop all buffers and perform final flushes."""
        with self._buffers_lock:
            buffers = list(self._buffers.values())
        for buf in buffers:
            await buf.stop()
        with self._buffers_lock:
            self._buffers.clear()
        self._started = False

    def enqueue(self, event: _UsageEvent) -> None:
        """Enqueue usage for the current auth user (or legacy global file)."""
        cache_key = self._resolve_record_key(None)
        self._buffer_for_key(cache_key).enqueue(event)

    async def record(
        self,
        provider_id: str,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        at_date: Optional[date] = None,
        user_id: str | None = None,
    ) -> None:
        """Record token usage for a given provider, model and date."""
        from datetime import datetime, timezone

        if at_date is None:
            at_date = date.today()
        cache_key = self._resolve_record_key(user_id)
        self._buffer_for_key(cache_key).enqueue(
            _UsageEvent(
                provider_id=provider_id,
                model_name=model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                date_str=at_date.isoformat(),
                now_iso=datetime.now(tz=timezone.utc).isoformat(
                    timespec="seconds",
                ),
            ),
        )

    async def _merged_data(
        self,
        user_id: str | None = None,
        aggregate_all: bool = False,
    ) -> dict:
        if aggregate_all:
            caches: list[dict] = []
            seen_users: set[str] = set()

            legacy_path = (WORKING_DIR / TOKEN_USAGE_FILE).expanduser()
            if legacy_path.is_file() or _LEGACY_KEY in self._buffers:
                caches.append(
                    await self._buffer_for_key(_LEGACY_KEY).get_merged_data(),
                )

            with self._buffers_lock:
                active_user_keys = [
                    k for k in self._buffers if k != _LEGACY_KEY
                ]
            for uid in sorted(active_user_keys):
                caches.append(await self._buffer_for_key(uid).get_merged_data())
                seen_users.add(uid)

            if USERS_DIR.is_dir():
                for user_dir in sorted(USERS_DIR.iterdir()):
                    if not user_dir.is_dir():
                        continue
                    uid = user_dir.name
                    if uid in seen_users:
                        continue
                    usage_file = user_dir / TOKEN_USAGE_FILE
                    if usage_file.is_file():
                        caches.append(
                            await self._buffer_for_key(uid).get_merged_data(),
                        )
                        seen_users.add(uid)
            return merge_usage_caches(caches)

        cache_key = user_id if user_id else _LEGACY_KEY
        return await self._buffer_for_key(cache_key).get_merged_data()

    async def _query(
        self,
        merged: dict,
        start_date: date,
        end_date: date,
        model_name: Optional[str],
        provider_id: Optional[str],
    ) -> list[TokenUsageRecord]:
        """Return per-day records from the merged data dict."""
        results: list[TokenUsageRecord] = []

        current = start_date
        while current <= end_date:
            date_str = current.isoformat()
            by_key = merged.get(date_str, {})
            for _key, entry in by_key.items():
                rec_provider = entry.get("provider_id", "")
                rec_model = entry.get("model_name") or _key
                if model_name is not None and rec_model != model_name:
                    continue
                if provider_id is not None and rec_provider != provider_id:
                    continue
                results.append(
                    TokenUsageRecord(
                        date=date_str,
                        provider_id=rec_provider,
                        model=rec_model,
                        prompt_tokens=entry.get("prompt_tokens", 0),
                        completion_tokens=entry.get("completion_tokens", 0),
                        call_count=entry.get("call_count", 0),
                    ),
                )
            current += timedelta(days=1)

        return results

    async def get_summary(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        model_name: Optional[str] = None,
        provider_id: Optional[str] = None,
        user_id: str | None = None,
        aggregate_all: bool = False,
    ) -> TokenUsageSummary:
        """Get aggregated token usage summary."""
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=30)

        merged = await self._merged_data(
            user_id=user_id,
            aggregate_all=aggregate_all,
        )

        records = await self._query(
            merged,
            start_date,
            end_date,
            model_name,
            provider_id,
        )

        total_prompt = 0
        total_completion = 0
        total_calls = 0
        by_model_raw: dict[str, dict] = {}
        by_date_raw: dict[str, dict] = {}

        for r in records:
            pt = r.prompt_tokens
            ct = r.completion_tokens
            calls = r.call_count
            total_prompt += pt
            total_completion += ct
            total_calls += calls

            model_key = (
                f"{r.provider_id}:{r.model}" if r.provider_id else r.model
            )
            bm = by_model_raw.setdefault(
                model_key,
                {
                    "provider_id": r.provider_id,
                    "model": r.model,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "call_count": 0,
                },
            )
            bm["prompt_tokens"] += pt
            bm["completion_tokens"] += ct
            bm["call_count"] += calls

            bd = by_date_raw.setdefault(
                r.date,
                {"prompt_tokens": 0, "completion_tokens": 0, "call_count": 0},
            )
            bd["prompt_tokens"] += pt
            bd["completion_tokens"] += ct
            bd["call_count"] += calls

        return TokenUsageSummary(
            total_prompt_tokens=total_prompt,
            total_completion_tokens=total_completion,
            total_calls=total_calls,
            by_model={
                k: TokenUsageByModel.model_validate(v)
                for k, v in sorted(by_model_raw.items())
            },
            by_date={
                k: TokenUsageStats.model_validate(v)
                for k, v in sorted(by_date_raw.items())
            },
        )

    async def get_details(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        model_name: Optional[str] = None,
        provider_id: Optional[str] = None,
        user_id: str | None = None,
        aggregate_all: bool = False,
    ) -> list[TokenUsageRecord]:
        """Get raw token usage records for frontend aggregation."""
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=30)

        merged = await self._merged_data(
            user_id=user_id,
            aggregate_all=aggregate_all,
        )

        return await self._query(
            merged,
            start_date,
            end_date,
            model_name,
            provider_id,
        )

    @classmethod
    def get_instance(cls) -> "TokenUsageManager":
        """Return the process-wide singleton ``TokenUsageManager``."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance


def get_token_usage_manager() -> TokenUsageManager:
    """Return the process-wide singleton ``TokenUsageManager``."""
    return TokenUsageManager.get_instance()
