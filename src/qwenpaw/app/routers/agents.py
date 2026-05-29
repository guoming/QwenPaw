# -*- coding: utf-8 -*-
"""Multi-agent management API.

Provides RESTful API for managing multiple agent instances.
"""

import json
import logging
from pathlib import Path
from fastapi import APIRouter, Body, HTTPException, Request

from ..deps import get_request_user_id, require_admin
from ..user_agent_registry import (
    list_user_agent_ids,
    provision_private_agent_from_template,
    purge_agent_for_all_users,
    purge_user_private_agent,
    resolve_user_workspace_dir,
    seed_agent_for_user,
    seed_user_for_all_users,
    user_owns_agent,
)
from fastapi import Path as PathParam
from pydantic import BaseModel, field_validator

from agentscope_runtime.engine.schemas.exception import (
    AppBaseException,
)

from ...agents.utils.file_handling import read_text_file_with_encoding_fallback
from ..utils import schedule_agent_reload
from ...config.config import (
    AgentProfileConfig,
    AgentProfileRef,
    ModelSlotConfig,
    load_agent_config,
    save_agent_config,
    generate_short_agent_id,
    sanitize_agent_id,
    validate_agent_id,
)
from ...config.utils import load_config, save_config
from ...agents.utils import copy_workspace_md_files, normalize_agent_language
from ...agents.skill_system import SkillPoolService, get_workspace_skills_dir
from ..multi_agent_manager import MultiAgentManager
from ...constant import WORKING_DIR

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])
templates_router = APIRouter(prefix="/agent-templates", tags=["agents"])


class AgentSummary(BaseModel):
    """Agent summary information."""

    id: str
    name: str
    description: str
    workspace_dir: str
    enabled: bool
    active_model: ModelSlotConfig | None = None


class AgentListResponse(BaseModel):
    """Response for listing agents."""

    agents: list[AgentSummary]


class ReorderAgentsRequest(BaseModel):
    """Request model for persisting agent order."""

    agent_ids: list[str]


class AgentTemplateSummary(BaseModel):
    """Agent template summary information."""

    id: str
    name: str
    description: str
    enabled: bool


class AgentTemplateListResponse(BaseModel):
    """Response for listing agent templates."""

    templates: list[AgentTemplateSummary]


class CreateAgentRequest(BaseModel):
    """Request model for creating a new agent.

    The ``id`` field is optional.  When provided the server uses it as
    the agent identifier (after sanitization); when omitted a random
    short UUID is generated automatically.
    """

    id: str | None = None
    name: str
    description: str = ""
    workspace_dir: str | None = None
    language: str | None = None
    skill_names: list[str] | None = None
    active_model: ModelSlotConfig | None = None

    @field_validator("id", mode="before")
    @classmethod
    def sanitize_id(cls, value: str | None) -> str | None:
        """Strip whitespace from the custom ID."""
        if value is None:
            return None
        if isinstance(value, str):
            sanitized = sanitize_agent_id(value)
            return sanitized if sanitized else None
        return value

    @field_validator("workspace_dir", mode="before")
    @classmethod
    def strip_workspace_dir(cls, value: str | None) -> str | None:
        """Strip accidental whitespace"""
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped if stripped else None
        return value


class CreateAgentFromTemplateRequest(BaseModel):
    """Request model for provisioning a private user agent from template."""

    template_agent_id: str
    name: str | None = None
    description: str | None = None
    workspace_dir: str | None = None
    skill_names: list[str] | None = None
    active_model: ModelSlotConfig | None = None


class UpdatePrivateAgentRequest(BaseModel):
    """Update metadata for a user-owned private agent."""

    name: str | None = None
    description: str | None = None


def _get_multi_agent_manager(request: Request) -> MultiAgentManager:
    """Get MultiAgentManager from app state."""
    if not hasattr(request.app.state, "multi_agent_manager"):
        raise HTTPException(
            status_code=500,
            detail="MultiAgentManager not initialized",
        )
    return request.app.state.multi_agent_manager


def _normalized_agent_order(config) -> list[str]:
    """Return a deduplicated agent order covering every configured agent."""
    profile_ids = list(config.agents.profiles.keys())
    ordered_ids: list[str] = []

    for agent_id in config.agents.agent_order:
        if agent_id in config.agents.profiles and agent_id not in ordered_ids:
            ordered_ids.append(agent_id)

    for agent_id in profile_ids:
        if agent_id not in ordered_ids:
            ordered_ids.append(agent_id)

    return ordered_ids


def _read_profile_description(workspace_dir: str) -> str:
    """Read description from PROFILE.md if exists."""
    try:
        profile_path = Path(workspace_dir) / "PROFILE.md"
        if not profile_path.exists():
            return ""

        content = read_text_file_with_encoding_fallback(profile_path).strip()
        lines = []
        in_identity = False

        for line in content.split("\n"):
            if line.strip().startswith("## 身份") or line.strip().startswith(
                "## Identity",
            ):
                in_identity = True
                continue
            if in_identity:
                if line.strip().startswith("##"):
                    break
                if line.strip() and not line.strip().startswith("#"):
                    lines.append(line.strip())

        return " ".join(lines)[:200] if lines else ""
    except Exception:  # noqa: E722
        return ""


@router.get(
    "",
    response_model=AgentListResponse,
    summary="List all agents",
    description="Get list of all configured agents",
)
async def list_agents(request: Request) -> AgentListResponse:
    """List all configured agents."""
    config = load_config()
    auth_user_id = getattr(request.state, "user_id", None)
    is_admin = bool(getattr(request.state, "is_admin", False))
    if is_admin:
        ordered_agent_ids = _normalized_agent_order(config)
    else:
        ordered_agent_ids = list_user_agent_ids(auth_user_id) if auth_user_id else []
    config_user_id = None if is_admin else auth_user_id

    agents = []
    for agent_id in ordered_agent_ids:
        agent_ref = config.agents.profiles.get(agent_id)
        try:
            agent_config = load_agent_config(
                agent_id,
                user_id=config_user_id,
            )
            description = agent_config.description or ""

            template_ws_dir = None
            if agent_ref is not None:
                template_ws_dir = agent_ref.workspace_dir
            elif agent_config.template_id:
                template_ref = config.agents.profiles.get(
                    agent_config.template_id,
                )
                if template_ref is not None:
                    template_ws_dir = template_ref.workspace_dir

            if template_ws_dir:
                profile_desc = _read_profile_description(template_ws_dir)
                if profile_desc:
                    if description.strip():
                        description = f"{description.strip()} | {profile_desc}"
                    else:
                        description = profile_desc

            active_model = agent_config.active_model
            if agent_ref is not None:
                workspace_dir = agent_ref.workspace_dir
                enabled = getattr(agent_ref, "enabled", True)
            else:
                workspace_dir = agent_config.workspace_dir or str(
                    resolve_user_workspace_dir(auth_user_id, agent_id),
                )
                enabled = True

            agents.append(
                AgentSummary(
                    id=agent_id,
                    name=agent_config.name,
                    description=description,
                    workspace_dir=workspace_dir,
                    enabled=enabled,
                    active_model=active_model,
                ),
            )
        except Exception:  # noqa: E722
            if agent_ref is None:
                logger.warning(
                    "Skip unknown user agent id '%s' for user '%s'",
                    agent_id,
                    auth_user_id,
                )
                continue
            agents.append(
                AgentSummary(
                    id=agent_id,
                    name=agent_id.title(),
                    description="",
                    workspace_dir=agent_ref.workspace_dir,
                    enabled=getattr(agent_ref, "enabled", True),
                ),
            )

    return AgentListResponse(agents=agents)


@templates_router.get(
    "",
    response_model=AgentTemplateListResponse,
    summary="List enabled agent templates",
    description="Get enabled templates that users can provision",
)
async def list_agent_templates(request: Request) -> AgentTemplateListResponse:
    """List enabled templates for self-provisioning."""
    _ = get_request_user_id(request)
    config = load_config()
    templates: list[AgentTemplateSummary] = []
    for agent_id in _normalized_agent_order(config):
        agent_ref = config.agents.profiles.get(agent_id)
        if not agent_ref or not getattr(agent_ref, "enabled", True):
            continue
        try:
            template_cfg = load_agent_config(agent_id, user_id=None)
            description = template_cfg.description or ""
            profile_desc = _read_profile_description(agent_ref.workspace_dir)
            if profile_desc:
                description = (
                    f"{description.strip()} | {profile_desc}"
                    if description.strip()
                    else profile_desc
                )
            templates.append(
                AgentTemplateSummary(
                    id=agent_id,
                    name=template_cfg.name,
                    description=description,
                    enabled=True,
                ),
            )
        except Exception:  # noqa: E722
            templates.append(
                AgentTemplateSummary(
                    id=agent_id,
                    name=agent_id.title(),
                    description="",
                    enabled=True,
                ),
            )
    return AgentTemplateListResponse(templates=templates)


@router.put(
    "/order",
    summary="Persist agent order",
    description="Save the full ordered list of configured agent IDs",
)
async def reorder_agents(
    request: Request,
    reorder_request: ReorderAgentsRequest = Body(...),
) -> dict:
    """Persist the full ordered list of agent IDs."""
    require_admin(request)
    config = load_config()
    configured_ids = list(config.agents.profiles.keys())

    if len(reorder_request.agent_ids) != len(set(reorder_request.agent_ids)):
        raise HTTPException(
            status_code=400,
            detail="Each configured agent ID must appear exactly once.",
        )

    if set(reorder_request.agent_ids) != set(configured_ids):
        raise HTTPException(
            status_code=400,
            detail="Each configured agent ID must appear exactly once.",
        )

    config.agents.agent_order = list(reorder_request.agent_ids)
    save_config(config)

    return {"success": True, "agent_ids": config.agents.agent_order}


@router.get(
    "/{agentId}",
    response_model=AgentProfileConfig,
    summary="Get agent details",
    description="Get complete configuration for a specific agent",
)
async def get_agent(
    request: Request,
    agentId: str = PathParam(...),
) -> AgentProfileConfig:
    """Get agent configuration for the authenticated user."""
    try:
        user_id = get_request_user_id(request)
        agent_config = load_agent_config(agentId, user_id=user_id)
        return agent_config
    except (ValueError, AppBaseException) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


def _generate_unique_id(existing_ids: set[str]) -> str:
    """Generate a unique random short agent ID.

    Raises:
        HTTPException: If a unique ID could not be generated.
    """
    max_attempts = 10
    for _ in range(max_attempts):
        candidate_id = generate_short_agent_id()
        if candidate_id not in existing_ids:
            return candidate_id
    raise HTTPException(
        status_code=500,
        detail="Failed to generate unique agent ID after 10 attempts",
    )


@router.post(
    "",
    response_model=AgentProfileRef,
    status_code=201,
    summary="Create new agent",
    description="Create a new agent with optional custom ID",
)
async def create_agent(
    http_request: Request,
    request: CreateAgentRequest = Body(...),
) -> AgentProfileRef:
    """Create a new agent.

    When ``request.id`` is provided, it is used as the agent identifier
    (validated for URL-safe characters, length, reserved words, and
    uniqueness).  Otherwise a random short UUID is generated.
    """
    require_admin(http_request)
    config = load_config()
    existing_ids = set(config.agents.profiles.keys())

    if request.id:
        try:
            validate_agent_id(request.id, existing_ids)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=str(e),
            ) from e
        new_id = request.id
    else:
        new_id = _generate_unique_id(existing_ids)

    workspace_dir = Path(
        request.workspace_dir or f"{WORKING_DIR}/workspaces/{new_id}",
    ).expanduser()
    workspace_dir.mkdir(parents=True, exist_ok=True)

    from ...config.config import (
        ChannelConfig,
        MCPConfig,
        HeartbeatConfig,
        ToolsConfig,
    )

    language = normalize_agent_language(
        request.language or config.agents.language or "en",
    )

    agent_config = AgentProfileConfig(
        id=new_id,
        name=request.name,
        description=request.description,
        workspace_dir=str(workspace_dir),
        language=language,
        channels=ChannelConfig(),
        mcp=MCPConfig(),
        heartbeat=HeartbeatConfig(),
        tools=ToolsConfig(),
        active_model=request.active_model,
    )

    _initialize_agent_workspace(
        workspace_dir,
        skill_names=(
            request.skill_names if request.skill_names is not None else []
        ),
        language=language,
    )

    agent_ref = AgentProfileRef(
        id=new_id,
        workspace_dir=str(workspace_dir),
        enabled=True,
    )

    config.agents.profiles[new_id] = agent_ref
    config.agents.agent_order = _normalized_agent_order(config)
    save_config(config)
    save_agent_config(new_id, agent_config, user_id=None)
    seed_user_for_all_users(new_id)

    logger.info(f"Created new agent: {new_id} (name={request.name})")

    return agent_ref


@router.post(
    "/from-template",
    response_model=AgentSummary,
    status_code=201,
    summary="Create private agent from template",
    description="Provision a private user copy from an enabled template",
)
async def create_agent_from_template(
    request: Request,
    payload: CreateAgentFromTemplateRequest = Body(...),
) -> AgentSummary:
    """Provision the current user's private agent copy from template."""
    user_id = get_request_user_id(request)
    config = load_config()
    template_id = payload.template_agent_id

    if template_id not in config.agents.profiles:
        raise HTTPException(
            status_code=404,
            detail=f"Template agent '{template_id}' not found",
        )
    template_ref = config.agents.profiles[template_id]
    if not getattr(template_ref, "enabled", True):
        raise HTTPException(
            status_code=409,
            detail=f"Template agent '{template_id}' is disabled",
        )
    try:
        private_id = provision_private_agent_from_template(user_id, template_id)
    except ValueError as exc:
        detail = str(exc)
        if "already exists" in detail:
            raise HTTPException(status_code=409, detail=detail) from exc
        raise HTTPException(status_code=404, detail=detail) from exc

    user_cfg = load_agent_config(private_id, user_id=user_id)
    if payload.name is not None:
        user_cfg.name = payload.name
    if payload.description is not None:
        user_cfg.description = payload.description
    if payload.workspace_dir is not None:
        user_cfg.workspace_dir = payload.workspace_dir
    if payload.active_model is not None:
        user_cfg.active_model = payload.active_model
    save_agent_config(private_id, user_cfg, user_id=user_id)

    if payload.skill_names:
        _install_initial_skills(
            resolve_user_workspace_dir(user_id, private_id),
            payload.skill_names,
        )

    description = user_cfg.description or ""
    profile_desc = _read_profile_description(template_ref.workspace_dir)
    if profile_desc:
        description = (
            f"{description.strip()} | {profile_desc}"
            if description.strip()
            else profile_desc
        )

    user_ws = resolve_user_workspace_dir(user_id, private_id)
    return AgentSummary(
        id=private_id,
        name=user_cfg.name,
        description=description,
        workspace_dir=str(user_ws),
        enabled=getattr(template_ref, "enabled", True),
        active_model=user_cfg.active_model,
    )


def _private_agent_summary(
    user_id: str,
    agent_id: str,
    *,
    config=None,
) -> AgentSummary:
    """Build list response entry for a user-owned private agent."""
    if config is None:
        config = load_config()
    user_cfg = load_agent_config(agent_id, user_id=user_id)
    description = user_cfg.description or ""
    template_ref = None
    if user_cfg.template_id:
        template_ref = config.agents.profiles.get(user_cfg.template_id)
    if template_ref is not None:
        profile_desc = _read_profile_description(template_ref.workspace_dir)
        if profile_desc:
            description = (
                f"{description.strip()} | {profile_desc}"
                if description.strip()
                else profile_desc
            )
    user_ws = resolve_user_workspace_dir(user_id, agent_id)
    return AgentSummary(
        id=agent_id,
        name=user_cfg.name,
        description=description,
        workspace_dir=str(user_ws),
        enabled=True,
        active_model=user_cfg.active_model,
    )


@router.patch(
    "/{agentId}/self",
    response_model=AgentSummary,
    summary="Update private agent",
    description="Update the current user's private agent metadata",
)
async def update_private_agent(
    request: Request,
    agentId: str = PathParam(...),
    payload: UpdatePrivateAgentRequest = Body(...),
) -> AgentSummary:
    """Update name/description for a user-owned private agent."""
    user_id = get_request_user_id(request)
    if not user_owns_agent(user_id, agentId):
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agentId}' not found",
        )

    user_cfg = load_agent_config(agentId, user_id=user_id)
    if payload.name is not None:
        user_cfg.name = payload.name
    if payload.description is not None:
        user_cfg.description = payload.description
    save_agent_config(agentId, user_cfg, user_id=user_id)
    schedule_agent_reload(request, agentId)
    return _private_agent_summary(user_id, agentId)


@router.delete(
    "/{agentId}/self",
    summary="Delete private agent",
    description="Delete the current user's private agent instance",
)
async def delete_private_agent(
    request: Request,
    agentId: str = PathParam(...),
) -> dict:
    """Remove a user-owned private agent and its workspace data."""
    user_id = get_request_user_id(request)
    if not user_owns_agent(user_id, agentId):
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agentId}' not found",
        )

    manager = _get_multi_agent_manager(request)
    await manager.stop_agent(agentId, user_id=user_id)
    try:
        purge_user_private_agent(user_id, agentId)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {"success": True, "agent_id": agentId}


@router.put(
    "/{agentId}",
    response_model=AgentProfileConfig,
    summary="Update agent",
    description="Update agent configuration and trigger reload",
)
async def update_agent(
    agentId: str = PathParam(...),
    agent_config: AgentProfileConfig = Body(...),
    request: Request = None,
) -> AgentProfileConfig:
    """Update agent configuration (global template)."""
    require_admin(request)
    config = load_config()

    if agentId not in config.agents.profiles:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agentId}' not found",
        )

    existing_config = load_agent_config(agentId, user_id=None)

    update_data = agent_config.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key != "id":
            setattr(existing_config, key, value)

    existing_config.id = agentId
    save_agent_config(agentId, existing_config, user_id=None)
    schedule_agent_reload(request, agentId)

    return agent_config


@router.delete(
    "/{agentId}",
    summary="Delete agent",
    description="Delete agent and workspace (cannot delete default agent)",
)
async def delete_agent(
    agentId: str = PathParam(...),
    request: Request = None,
) -> dict:
    """Delete an agent."""
    require_admin(request)
    config = load_config()

    if agentId not in config.agents.profiles:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agentId}' not found",
        )

    if agentId == "default":
        raise HTTPException(
            status_code=400,
            detail="Cannot delete the default agent",
        )

    manager = _get_multi_agent_manager(request)
    await manager.stop_agent(agentId)
    purge_agent_for_all_users(agentId)

    del config.agents.profiles[agentId]
    config.agents.agent_order = _normalized_agent_order(config)
    save_config(config)

    return {"success": True, "agent_id": agentId}


@router.patch(
    "/{agentId}/toggle",
    summary="Toggle agent enabled state",
    description="Enable or disable an agent (cannot disable default agent)",
)
async def toggle_agent_enabled(
    agentId: str = PathParam(...),
    enabled: bool = Body(..., embed=True),
    request: Request = None,
) -> dict:
    """Toggle agent enabled state."""
    require_admin(request)
    config = load_config()

    if agentId not in config.agents.profiles:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agentId}' not found",
        )

    if agentId == "default":
        raise HTTPException(
            status_code=400,
            detail="Cannot disable the default agent",
        )

    agent_ref = config.agents.profiles[agentId]
    manager = _get_multi_agent_manager(request)

    if not enabled and getattr(agent_ref, "enabled", True):
        await manager.stop_agent(agentId)

    agent_ref.enabled = enabled
    save_config(config)

    if enabled:
        try:
            await manager.get_agent(agentId)
            logger.info(f"Agent {agentId} started successfully")
        except Exception as e:
            logger.error(f"Failed to start agent {agentId}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Agent enabled but failed to start: {str(e)}",
            ) from e

    return {
        "success": True,
        "agent_id": agentId,
        "enabled": enabled,
    }


def _apply_workspace_md_templates(
    workspace_dir: Path,
    language: str,
    *,
    md_template_id: str | None,
) -> None:
    """Copy common and template-specific markdown files for a workspace."""
    copy_workspace_md_files(
        language,
        workspace_dir,
        md_template_id=md_template_id,
    )


def _ensure_heartbeat_file(workspace_dir: Path, language: str) -> None:
    """Create the default HEARTBEAT.md if it is missing."""
    heartbeat_file = workspace_dir / "HEARTBEAT.md"
    if heartbeat_file.exists():
        return

    default_heartbeat_mds = {
        "zh": """# Heartbeat checklist
- 扫描收件箱紧急邮件
- 查看未来 2h 的日历
- 检查待办是否卡住
- 若安静超过 8h，轻量 check-in
""",
        "en": """# Heartbeat checklist
- Scan inbox for urgent email
- Check calendar for next 2h
- Check tasks for blockers
- Light check-in if quiet for 8h
""",
        "ru": """# Heartbeat checklist
- Проверить входящие на срочные письма
- Просмотреть календарь на ближайшие 2 часа
- Проверить задачи на наличие блокировок
- Лёгкая проверка при отсутствии активности более 8 часов
""",
    }
    heartbeat_content = default_heartbeat_mds.get(
        language,
        default_heartbeat_mds["en"],
    )
    with open(heartbeat_file, "w", encoding="utf-8") as file:
        file.write(heartbeat_content.strip())


def _install_initial_skills(
    workspace_dir: Path,
    skill_names: list[str] | None,
) -> None:
    """Install requested initial skills from the skill pool."""
    if not skill_names:
        return

    pool_service = SkillPoolService()
    for skill_name in skill_names:
        try:
            result = pool_service.download_to_workspace(
                skill_name=skill_name,
                workspace_dir=workspace_dir,
                overwrite=False,
            )
            if result.get("success"):
                continue
            logger.warning(
                "Failed to install initial skill %s for %s: %s",
                skill_name,
                workspace_dir,
                result.get("reason", "unknown"),
            )
        except Exception as e:
            logger.warning(
                "Failed to install initial skill %s for %s: %s",
                skill_name,
                workspace_dir,
                e,
            )


def _initialize_agent_workspace(
    workspace_dir: Path,
    skill_names: list[str] | None = None,
    md_template_id: str | None = None,
    language: str | None = None,
) -> None:
    """Initialize agent workspace with only explicitly requested skills."""
    from ...config import load_config as load_global_config

    (workspace_dir / "sessions").mkdir(exist_ok=True)
    (workspace_dir / "memory").mkdir(exist_ok=True)
    get_workspace_skills_dir(workspace_dir).mkdir(exist_ok=True)

    config = load_global_config()
    if not language:
        language = config.agents.language or "zh"

    _apply_workspace_md_templates(
        workspace_dir,
        language,
        md_template_id=md_template_id,
    )
    _ensure_heartbeat_file(workspace_dir, language)
    _install_initial_skills(workspace_dir, skill_names)

    jobs_file = workspace_dir / "jobs.json"
    if not jobs_file.exists():
        with open(jobs_file, "w", encoding="utf-8") as file:
            json.dump(
                {"version": 1, "jobs": []},
                file,
                ensure_ascii=False,
                indent=2,
            )

    chats_file = workspace_dir / "chats.json"
    if not chats_file.exists():
        with open(chats_file, "w", encoding="utf-8") as file:
            json.dump(
                {"version": 1, "chats": []},
                file,
                ensure_ascii=False,
                indent=2,
            )
