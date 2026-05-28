# -*- coding: utf-8 -*-
import json
from pathlib import Path

import pytest

from qwenpaw.config.config import (
    AgentProfileConfig,
    agent_config_cache_key,
    load_agent_config,
    resolve_agent_config_path,
    save_agent_config,
)
from qwenpaw.config.utils import load_config, save_config


@pytest.fixture
def isolated_dirs(tmp_path, monkeypatch):
    working = tmp_path / "work"
    users = working / "users"
    secret = tmp_path / "secret"
    working.mkdir()
    users.mkdir()
    secret.mkdir()
    monkeypatch.setattr("qwenpaw.constant.WORKING_DIR", working)
    monkeypatch.setattr("qwenpaw.constant.USERS_DIR", users)
    monkeypatch.setattr("qwenpaw.constant.SECRET_DIR", secret)

    ws = working / "workspaces" / "bot1"
    ws.mkdir(parents=True)
    template = {
        "id": "bot1",
        "name": "Template Bot",
        "description": "global",
    }
    (ws / "agent.json").write_text(
        json.dumps(template),
        encoding="utf-8",
    )
    cfg = load_config()
    from qwenpaw.config.config import AgentProfileRef

    cfg.agents.profiles["bot1"] = AgentProfileRef(
        id="bot1",
        workspace_dir=str(ws),
        enabled=True,
    )
    save_config(cfg)
    return working, users, ws


def test_resolve_user_path(isolated_dirs):
    _, users, _ = isolated_dirs
    path = resolve_agent_config_path("bot1", user_id="u_test")
    assert path == users / "u_test" / "agent_configs" / "bot1" / "agent.json"


def test_load_user_config_roundtrip(isolated_dirs):
    working, users, ws = isolated_dirs
    user_path = users / "u1" / "agent_configs" / "bot1" / "agent.json"
    user_path.parent.mkdir(parents=True, exist_ok=True)
    user_data = {
        "id": "bot1",
        "name": "User Bot",
        "description": "per-user",
    }
    user_path.write_text(json.dumps(user_data), encoding="utf-8")

    loaded = load_agent_config("bot1", user_id="u1")
    assert loaded.name == "User Bot"

    global_loaded = load_agent_config("bot1", user_id=None)
    assert global_loaded.name == "Template Bot"


def test_cache_key():
    assert agent_config_cache_key("a", None) == "a:"
    assert agent_config_cache_key("a", "u1") == "a:u1"
