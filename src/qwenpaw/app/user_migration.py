# -*- coding: utf-8 -*-
"""Migrate legacy single-user data into the first admin's user directory."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from .. import constant
from ..config.utils import load_config

logger = logging.getLogger(__name__)

_MIGRATION_MARKER = ".user_data_migrated"


def _marker_path() -> Path:
    return constant.WORKING_DIR / _MIGRATION_MARKER


def migration_completed() -> bool:
    return _marker_path().is_file()


def _find_admin_user_id() -> str | None:
    from .auth import _get_users, _load_auth_data

    data = _load_auth_data()
    users = _get_users(data)
    for user in users:
        if user.get("is_admin"):
            return user.get("user_id")
    if users:
        return users[0].get("user_id")
    return None


def _legacy_has_data() -> bool:
    working = constant.WORKING_DIR
    if (working / "inbox_events.json").is_file():
        return True
    workspaces = working / "workspaces"
    if workspaces.is_dir():
        for agent_dir in workspaces.iterdir():
            if not agent_dir.is_dir():
                continue
            if (agent_dir / "chats.json").is_file():
                return True
    return False


def migrate_legacy_to_admin_user() -> bool:
    """Copy legacy runtime data to ``users/<admin_id>/``. Returns True if ran."""
    if migration_completed():
        return False
    if not _legacy_has_data():
        _marker_path().write_text("skipped\n", encoding="utf-8")
        return False

    admin_id = _find_admin_user_id()
    if not admin_id:
        logger.info(
            "Legacy data detected but no registered user; "
            "migration deferred until first registration",
        )
        return False

    user_root = constant.USERS_DIR / admin_id
    config = load_config()

    for agent_id in config.agents.profiles:
        agent_ref = config.agents.profiles[agent_id]
        template_ws = Path(agent_ref.workspace_dir).expanduser()

        legacy_data = template_ws
        if (constant.WORKING_DIR / "workspaces" / agent_id).is_dir():
            legacy_data = constant.WORKING_DIR / "workspaces" / agent_id

        dest_data = user_root / "agent_data" / agent_id
        if legacy_data.is_dir() and not dest_data.exists():
            shutil.copytree(legacy_data, dest_data, dirs_exist_ok=True)

        dest_cfg = user_root / "agent_configs" / agent_id / "agent.json"
        src_cfg = template_ws / "agent.json"
        if src_cfg.is_file() and not dest_cfg.exists():
            dest_cfg.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_cfg, dest_cfg)

        dest_coding = user_root / "agent_workspaces" / agent_id
        dest_coding.mkdir(parents=True, exist_ok=True)
        if template_ws.is_dir() and not any(dest_coding.iterdir()):
            for item in template_ws.iterdir():
                target = dest_coding / item.name
                if item.is_dir():
                    shutil.copytree(item, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, target)

    legacy_inbox = constant.WORKING_DIR / "inbox_events.json"
    dest_inbox = user_root / "inbox_events.json"
    if legacy_inbox.is_file() and not dest_inbox.exists():
        shutil.copy2(legacy_inbox, dest_inbox)

    _marker_path().write_text(f"migrated_to={admin_id}\n", encoding="utf-8")
    logger.info("Migrated legacy data to user %s", admin_id)
    return True
