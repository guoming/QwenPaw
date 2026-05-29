# -*- coding: utf-8 -*-
"""Per-user agent config seeding and cleanup."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from .. import constant
from ..config.config import resolve_agent_config_path
from ..config.utils import load_config

logger = logging.getLogger(__name__)


def resolve_user_workspace_dir(user_id: str, agent_id: str) -> Path:
    """Per-user agent workspace (markdown templates, coding tree root)."""
    return constant.USERS_DIR / user_id / "agent_workspaces" / agent_id


def list_user_agent_workspace_dirs(agent_id: str) -> list[Path]:
    """Return per-user workspace directories for *agent_id* (for admin rollup)."""
    dirs: list[Path] = []
    users_root = constant.USERS_DIR
    if not users_root.is_dir():
        return dirs
    for user_dir in sorted(users_root.iterdir()):
        if not user_dir.is_dir():
            continue
        ws = user_dir / "agent_workspaces" / agent_id
        if ws.is_dir():
            dirs.append(ws.resolve())
    return dirs


def _dir_has_entries(path: Path) -> bool:
    if not path.is_dir():
        return False
    try:
        return any(path.iterdir())
    except OSError:
        return False


def seed_user_workspace_from_template(
    user_ws: Path,
    template_dir: Path,
    agent_id: str,
) -> None:
    """Copy global/legacy workspace files into the user's workspace once."""
    user_ws.mkdir(parents=True, exist_ok=True)
    if _dir_has_entries(user_ws):
        return

    legacy = constant.WORKING_DIR / "workspaces" / agent_id
    sources: list[Path] = []
    if legacy.is_dir() and _dir_has_entries(legacy):
        sources.append(legacy)
    template_resolved = template_dir.expanduser().resolve()
    if template_dir.is_dir() and _dir_has_entries(template_dir):
        if not sources or template_resolved != sources[0].resolve():
            sources.append(template_dir)

    for src in sources:
        for item in src.iterdir():
            dest = user_ws / item.name
            if dest.exists():
                continue
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)
        if _dir_has_entries(user_ws):
            break


def list_all_user_ids() -> list[str]:
    """List registered user IDs that have a data directory."""
    users_dir = constant.USERS_DIR
    if not users_dir.is_dir():
        return []
    return [p.name for p in users_dir.iterdir() if p.is_dir()]


def user_owns_agent(user_id: str | None, agent_id: str) -> bool:
    """Return True if *agent_id* is provisioned under *user_id*."""
    if not user_id:
        return False
    return agent_id in set(list_user_agent_ids(user_id))


def agent_available_for_user(user_id: str | None, agent_id: str) -> bool:
    """Return True if *agent_id* is a global template or owned by *user_id*."""
    config = load_config()
    if agent_id in config.agents.profiles:
        return True
    return user_owns_agent(user_id, agent_id)


def is_agent_enabled_for_user(user_id: str | None, agent_id: str) -> bool:
    """Return whether *agent_id* may run for *user_id*."""
    config = load_config()
    if agent_id in config.agents.profiles:
        return getattr(config.agents.profiles[agent_id], "enabled", True)
    return user_owns_agent(user_id, agent_id)


def list_user_agent_ids(user_id: str) -> list[str]:
    """Return agent IDs that have user-owned config copies."""
    cfg_root = constant.USERS_DIR / user_id / "agent_configs"
    if not cfg_root.is_dir():
        return []
    ids: list[str] = []
    for agent_dir in sorted(cfg_root.iterdir()):
        if not agent_dir.is_dir():
            continue
        if (agent_dir / "agent.json").is_file():
            ids.append(agent_dir.name)
    return ids


def seed_agent_for_user(user_id: str, agent_id: str) -> None:
    """Copy global agent template into the user's config directory."""
    dest = resolve_agent_config_path(agent_id, user_id=user_id)
    if dest.exists():
        return

    src = resolve_agent_config_path(agent_id, user_id=None)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.exists():
        shutil.copy2(src, dest)
    else:
        from ..config.config import (
            build_fallback_agent_profile_config,
            save_agent_config,
        )

        config = load_config()
        fallback = build_fallback_agent_profile_config(agent_id, config)
        save_agent_config(agent_id, fallback, user_id=user_id)

    data_dir = constant.USERS_DIR / user_id / "agent_data" / agent_id
    data_dir.mkdir(parents=True, exist_ok=True)

    template_dir = Path(
        load_config().agents.profiles[agent_id].workspace_dir,
    ).expanduser()
    user_ws = resolve_user_workspace_dir(user_id, agent_id)
    seed_user_workspace_from_template(user_ws, template_dir, agent_id)

    logger.debug("Seeded agent %s for user %s", agent_id, user_id)


def provision_private_agent_from_template(
    user_id: str,
    template_agent_id: str,
) -> str:
    """Copy a global template into a new user-owned agent instance.

    The private agent reuses *template_agent_id* as its id so per-user
    workspace folders match the default layout
    (``agent_workspaces/<template_agent_id>``).
    """
    from ..config.config import load_agent_config, save_agent_config

    config = load_config()
    if template_agent_id not in config.agents.profiles:
        raise ValueError(f"Unknown template agent: {template_agent_id}")

    if template_agent_id in list_user_agent_ids(user_id):
        raise ValueError(
            f"Agent '{template_agent_id}' already exists for this user",
        )

    new_id = template_agent_id

    template_cfg = load_agent_config(template_agent_id, user_id=None)
    user_ws = resolve_user_workspace_dir(user_id, new_id)
    template_dir = Path(
        config.agents.profiles[template_agent_id].workspace_dir,
    ).expanduser()

    new_cfg = template_cfg.model_copy(deep=True)
    new_cfg.id = new_id
    new_cfg.template_id = template_agent_id
    new_cfg.workspace_dir = str(user_ws)

    save_agent_config(new_id, new_cfg, user_id=user_id)

    data_dir = constant.USERS_DIR / user_id / "agent_data" / new_id
    data_dir.mkdir(parents=True, exist_ok=True)
    seed_user_workspace_from_template(user_ws, template_dir, template_agent_id)

    logger.debug(
        "Provisioned private agent %s from template %s for user %s",
        new_id,
        template_agent_id,
        user_id,
    )
    return new_id


def seed_all_agents_for_user(user_id: str) -> None:
    """Seed all configured agents for a newly registered user."""
    for agent_id in load_config().agents.profiles:
        seed_agent_for_user(user_id, agent_id)


def seed_user_for_all_users(agent_id: str) -> None:
    """Seed a new global agent for every existing user."""
    for uid in list_all_user_ids():
        seed_agent_for_user(uid, agent_id)


def purge_user_private_agent(user_id: str, agent_id: str) -> None:
    """Remove one user-owned private agent instance and its data."""
    if not user_owns_agent(user_id, agent_id):
        raise ValueError(f"Agent '{agent_id}' not found for user")
    for sub in ("agent_configs", "agent_data", "agent_workspaces"):
        path = constant.USERS_DIR / user_id / sub / agent_id
        if path.is_dir():
            shutil.rmtree(path)
        elif path.is_file():
            path.unlink(missing_ok=True)
    logger.debug("Purged private agent %s for user %s", agent_id, user_id)


def purge_agent_for_all_users(agent_id: str) -> None:
    """Remove per-user data for an agent that was deleted globally."""
    for uid in list_all_user_ids():
        for sub in ("agent_configs", "agent_data", "agent_workspaces"):
            path = constant.USERS_DIR / uid / sub / agent_id
            if path.is_dir():
                shutil.rmtree(path)
            elif path.is_file():
                path.unlink(missing_ok=True)


def resolve_user_agent_template_workspace_dir(
    user_id: str,
    agent_id: str,
) -> Path | None:
    """Return the global template workspace used to seed a user-private agent."""
    import json

    cfg_path = resolve_agent_config_path(agent_id, user_id=user_id)
    if not cfg_path.is_file():
        return None
    with open(cfg_path, encoding="utf-8") as f:
        data = json.load(f)
    template_id = data.get("template_id")
    config = load_config()
    if template_id and template_id in config.agents.profiles:
        return Path(
            config.agents.profiles[template_id].workspace_dir,
        ).expanduser()
    workspace_dir = data.get("workspace_dir")
    if workspace_dir:
        return Path(workspace_dir).expanduser()
    return None


def ensure_user_agent_copy(user_id: str, agent_id: str) -> None:
    """Ensure the user has a config copy (lazy seed)."""
    if resolve_agent_config_path(agent_id, user_id=user_id).exists():
        return
    seed_agent_for_user(user_id, agent_id)
