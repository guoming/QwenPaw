# -*- coding: utf-8 -*-
"""Tests for Workspace class."""
import tempfile
from pathlib import Path
import pytest


@pytest.mark.asyncio
async def test_workspace_creation():
    """Test workspace instance creation."""
    from qwenpaw.app.workspace import Workspace

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_dir = Path(tmpdir) / "test_agent"
        workspace = Workspace(
            agent_id="test123",
            workspace_dir=str(workspace_dir),
        )

        assert workspace.agent_id == "test123"
        assert workspace.workspace_dir == workspace_dir
        assert workspace_dir.exists()
        assert not workspace._started  # pylint: disable=W0212


@pytest.mark.asyncio
async def test_workspace_components_none_before_start():
    """Test that workspace components are None before start()."""
    from qwenpaw.app.workspace import Workspace

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_dir = Path(tmpdir) / "test_agent"
        workspace = Workspace(
            agent_id="test123",
            workspace_dir=str(workspace_dir),
        )

        assert workspace.runner is None
        assert workspace.channel_manager is None
        assert workspace.memory_manager is None
        assert workspace.mcp_manager is None
        assert workspace.cron_manager is None
        assert workspace.chat_manager is None


@pytest.mark.asyncio
async def test_workspace_default_agent():
    """Test workspace with 'default' agent ID."""
    from qwenpaw.app.workspace import Workspace

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_dir = Path(tmpdir) / "default"
        workspace = Workspace(
            agent_id="default",
            workspace_dir=str(workspace_dir),
        )

        assert workspace.agent_id == "default"
        assert workspace.workspace_dir.name == "default"


@pytest.mark.asyncio
async def test_workspace_short_uuid_agent():
    """Test workspace with short UUID agent ID."""
    from qwenpaw.app.workspace import Workspace
    from qwenpaw.config.config import generate_short_agent_id

    short_id = generate_short_agent_id()

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_dir = Path(tmpdir) / short_id
        workspace = Workspace(
            agent_id=short_id,
            workspace_dir=str(workspace_dir),
        )

        assert workspace.agent_id == short_id
        assert len(workspace.agent_id) == 6
        assert workspace.workspace_dir.name == short_id


def test_workspace_uses_per_user_workspace_dir(monkeypatch, tmp_path):
    """Authenticated users read/write under users/<uid>/agent_workspaces/."""
    from qwenpaw.app.workspace import Workspace
    from qwenpaw import constant

    users = tmp_path / "users"
    working = tmp_path / "work"
    monkeypatch.setattr(constant, "USERS_DIR", users)
    monkeypatch.setattr(constant, "WORKING_DIR", working)

    template = working / "workspaces" / "yaboyE"
    template.mkdir(parents=True)
    (template / "SOUL.md").write_text("# soul", encoding="utf-8")

    ws = Workspace(
        agent_id="yaboyE",
        workspace_dir=str(template),
        user_id="user_a",
    )

    expected = users / "user_a" / "agent_workspaces" / "yaboyE"
    assert ws.workspace_dir == expected
    assert (expected / "SOUL.md").read_text() == "# soul"
    assert ws.data_dir == users / "user_a" / "agent_data" / "yaboyE"


def test_workspace_repr():
    """Test workspace string representation."""
    from qwenpaw.app.workspace import Workspace

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_dir = Path(tmpdir) / "test_agent"
        workspace = Workspace(
            agent_id="test123",
            workspace_dir=str(workspace_dir),
        )

        repr_str = repr(workspace)
        assert "test123" in repr_str
        assert "stopped" in repr_str
        assert "Workspace" in repr_str
