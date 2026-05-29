# -*- coding: utf-8 -*-
import json

import pytest

from qwenpaw.app.user_agent_registry import (
    provision_private_agent_from_template,
    purge_agent_for_all_users,
    seed_agent_for_user,
    seed_all_agents_for_user,
)
from qwenpaw.config.config import resolve_agent_config_path
from qwenpaw.config.utils import load_config, save_config


@pytest.fixture
def registry_env(tmp_path, monkeypatch):
    working = tmp_path / "work"
    users = working / "users"
    working.mkdir()
    users.mkdir()
    monkeypatch.setattr("qwenpaw.constant.WORKING_DIR", working)
    monkeypatch.setattr("qwenpaw.constant.USERS_DIR", users)
    monkeypatch.setattr("qwenpaw.constant.SECRET_DIR", tmp_path / "secret")

    ws = working / "workspaces" / "a1"
    ws.mkdir(parents=True)
    (ws / "agent.json").write_text(
        json.dumps({"id": "a1", "name": "A"}),
        encoding="utf-8",
    )
    from qwenpaw.config.config import AgentProfileRef

    cfg = load_config()
    cfg.agents.profiles["a1"] = AgentProfileRef(
        id="a1",
        workspace_dir=str(ws),
        enabled=True,
    )
    save_config(cfg)
    return users


def test_seed_skips_existing(registry_env):
    seed_agent_for_user("u1", "a1")
    path = resolve_agent_config_path("a1", user_id="u1")
    assert path.exists()
    path.write_text('{"id":"a1","name":"Custom"}', encoding="utf-8")
    seed_agent_for_user("u1", "a1")
    assert "Custom" in path.read_text()


def test_seed_copies_workspace_template(registry_env):
    users = registry_env
    template = users.parent / "workspaces" / "a1"
    (template / "IDENTITY.md").write_text("id", encoding="utf-8")
    seed_agent_for_user("u3", "a1")
    user_ws = users / "u3" / "agent_workspaces" / "a1"
    assert (user_ws / "IDENTITY.md").read_text() == "id"


def test_seed_does_not_copy_runtime_chat_state(registry_env):
    users = registry_env
    template = users.parent / "workspaces" / "a1"
    (template / "chats.json").write_text("{}", encoding="utf-8")
    (template / "jobs.json").write_text("{}", encoding="utf-8")
    (template / "sessions").mkdir(exist_ok=True)
    (template / "sessions" / "s.json").write_text("{}", encoding="utf-8")

    seed_agent_for_user("u4", "a1")

    data_dir = users / "u4" / "agent_data" / "a1"
    assert data_dir.is_dir()
    assert not (data_dir / "chats.json").exists()
    assert not (data_dir / "jobs.json").exists()
    assert not (data_dir / "sessions").exists()


def test_provision_private_agent_uses_template_id(registry_env):
    users = registry_env
    agent_id = provision_private_agent_from_template("u5", "a1")
    assert agent_id == "a1"
    user_ws = users / "u5" / "agent_workspaces" / "a1"
    assert user_ws.is_dir()
    assert (users / "u5" / "agent_configs" / "a1" / "agent.json").is_file()


def test_provision_private_agent_rejects_duplicate(registry_env):
    provision_private_agent_from_template("u6", "a1")
    with pytest.raises(ValueError, match="already exists"):
        provision_private_agent_from_template("u6", "a1")


def test_seed_all_and_purge(registry_env):
    users = registry_env
    seed_all_agents_for_user("u2")
    assert (users / "u2" / "agent_configs" / "a1" / "agent.json").exists()
    assert (users / "u2" / "agent_data" / "a1").is_dir()
    purge_agent_for_all_users("a1")
    assert not (users / "u2" / "agent_configs" / "a1").exists()
