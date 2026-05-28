# -*- coding: utf-8 -*-
"""MultiAgentManager: Manages multiple agent workspaces with lazy loading.

Provides centralized management for multiple Workspace objects,
including lazy loading, lifecycle management, and hot reloading.
"""
import asyncio
import logging
import time
from typing import Dict, Set

from agentscope_runtime.engine.schemas.exception import (
    ConfigurationException,
)

from .user_agent_registry import ensure_user_agent_copy
from .workspace import Workspace
from ..config.utils import load_config

logger = logging.getLogger(__name__)


def _agent_cache_key(agent_id: str, user_id: str | None = None) -> str:
    return f"{agent_id}:{user_id}" if user_id else agent_id


class MultiAgentManager:
    """Manages multiple agent workspaces.

    Features:
    - Lazy loading: Workspaces are created only when first requested
    - Lifecycle management: Start, stop, reload workspaces
    - Thread-safe: Uses async lock for concurrent access
    - Hot reload: Reload individual workspaces without affecting others
    - Parallel startup: Multiple agents start concurrently via
      fine-grained locking (lock released during slow workspace init)
    """

    def __init__(self):
        """Initialize multi-agent manager."""
        self.agents: Dict[str, Workspace] = {}
        self._lock = asyncio.Lock()
        self._pending_starts: Dict[str, asyncio.Event] = {}
        self._cleanup_tasks: Set[asyncio.Task] = set()
        logger.debug("MultiAgentManager initialized")

    async def get_agent(
        self,
        agent_id: str,
        user_id: str | None = None,
    ) -> Workspace:
        """Get agent workspace by ID (lazy loading with dedup).

        Args:
            agent_id: Agent ID to retrieve
            user_id: Optional user ID for per-user runtime isolation

        Returns:
            Workspace: The requested workspace instance
        """
        cache_key = _agent_cache_key(agent_id, user_id)

        if cache_key in self.agents:
            logger.debug(f"Returning cached agent: {cache_key}")
            return self.agents[cache_key]

        should_start = False
        event = None
        agent_ref = None

        async with self._lock:
            if cache_key in self.agents:
                return self.agents[cache_key]

            if cache_key in self._pending_starts:
                event = self._pending_starts[cache_key]
            else:
                config = load_config()
                if agent_id not in config.agents.profiles:
                    raise ConfigurationException(
                        config_key="agent",
                        message=(
                            f"Agent '{agent_id}' not found in configuration. "
                            f"Available agents: "
                            f"{list(config.agents.profiles.keys())}"
                        ),
                    )
                agent_ref = config.agents.profiles[agent_id]
                event = asyncio.Event()
                self._pending_starts[cache_key] = event
                should_start = True

        if not should_start:
            await event.wait()
            if cache_key in self.agents:
                return self.agents[cache_key]
            raise ConfigurationException(
                config_key="agent",
                message=f"Agent '{agent_id}' failed to initialize",
            )

        if user_id:
            ensure_user_agent_copy(user_id, agent_id)

        t0 = time.perf_counter()
        logger.debug(f"Creating new workspace: {cache_key}")
        instance = Workspace(
            agent_id=agent_id,
            workspace_dir=agent_ref.workspace_dir,
            user_id=user_id,
        )

        try:
            await instance.start()
            instance.set_manager(self)

            async with self._lock:
                self.agents[cache_key] = instance

            elapsed = time.perf_counter() - t0
            logger.debug(
                f"Workspace created and started: {cache_key} "
                f"({elapsed:.3f}s)",
            )
            return instance
        except Exception as e:
            logger.error(f"Failed to start workspace {cache_key}: {e}")
            raise
        finally:
            async with self._lock:
                self._pending_starts.pop(cache_key, None)
            event.set()

    async def _graceful_stop_old_instance(
        self,
        old_instance: Workspace,
        agent_id: str,
    ) -> None:
        """Gracefully stop old instance after checking for active tasks.

        If active tasks exist, schedule delayed cleanup in background.
        Otherwise, stop immediately.

        Args:
            old_instance: The old workspace instance to stop
            agent_id: Agent ID for logging
        """
        has_active = await old_instance.task_tracker.has_active_tasks()

        if has_active:
            # Active tasks - schedule delayed cleanup in background
            active_tasks = await old_instance.task_tracker.list_active_tasks()
            logger.info(
                f"Old workspace instance has {len(active_tasks)} active "
                f"task(s): {active_tasks}. Scheduling delayed cleanup for "
                f"{agent_id}.",
            )

            async def delayed_cleanup():
                """Wait for tasks to complete, then stop old instance."""
                try:
                    # Wait up to 1 minutes for tasks to complete
                    completed = await old_instance.task_tracker.wait_all_done(
                        timeout=60.0,
                    )
                    if completed:
                        logger.info(
                            f"All tasks completed for old instance "
                            f"{agent_id}. Stopping now.",
                        )
                    else:
                        logger.warning(
                            f"Timeout waiting for tasks to complete for "
                            f"{agent_id}. Forcing stop after 5 minutes.",
                        )

                    await old_instance.stop(final=False)
                    logger.info(
                        f"Old workspace instance stopped: {agent_id}. "
                        f"Delayed cleanup completed.",
                    )
                except Exception as e:
                    logger.warning(
                        f"Error during delayed cleanup for {agent_id}: {e}. "
                        f"New instance is serving requests.",
                    )

            # Create background task for delayed cleanup and track it
            cleanup_task = asyncio.create_task(delayed_cleanup())
            self._cleanup_tasks.add(cleanup_task)

            def _on_cleanup_done(task: asyncio.Task) -> None:
                """Remove task from tracking set and log errors."""
                self._cleanup_tasks.discard(task)
                if task.cancelled():
                    logger.info(
                        f"Delayed cleanup task for {agent_id} was cancelled.",
                    )
                    return
                exc = task.exception()
                if exc is not None:
                    logger.warning(
                        f"Error in delayed cleanup task for {agent_id}: "
                        f"{exc}.",
                    )

            cleanup_task.add_done_callback(_on_cleanup_done)
            logger.info(
                f"Zero-downtime reload completed: {agent_id}. "
                f"Old instance cleanup scheduled in background.",
            )
        else:
            # No active tasks - stop immediately
            logger.debug(
                f"No active tasks in old instance {agent_id}. "
                f"Stopping immediately.",
            )
            try:
                await old_instance.stop(final=False)
                logger.info(
                    f"Old workspace instance stopped: {agent_id}. "
                    f"Zero-downtime reload completed.",
                )
            except Exception as e:
                logger.warning(
                    f"Failed to stop old workspace instance for "
                    f"{agent_id}: {e}. "
                    f"New instance is active and serving requests.",
                )

    async def stop_agent(
        self,
        agent_id: str,
        user_id: str | None = None,
    ) -> bool:
        """Stop agent instance(s).

        When *user_id* is omitted, stops all cached instances for *agent_id*.
        """
        if user_id is not None:
            return await self._stop_cache_key(
                _agent_cache_key(agent_id, user_id),
            )

        stopped = False
        keys = [
            key
            for key in list(self.agents.keys())
            if key == agent_id or key.startswith(f"{agent_id}:")
        ]
        for key in keys:
            if await self._stop_cache_key(key):
                stopped = True
        return stopped

    async def _stop_cache_key(self, cache_key: str) -> bool:
        async with self._lock:
            if cache_key not in self.agents:
                logger.warning(f"Agent not running: {cache_key}")
                return False

            instance = self.agents[cache_key]
            await instance.stop()
            del self.agents[cache_key]
            logger.info(f"Agent stopped and removed: {cache_key}")
            return True

    def _cache_keys_for_agent(
        self,
        agent_id: str,
        user_id: str | None = None,
    ) -> list[str]:
        """Return running cache keys for ``agent_id``.

        When ``user_id`` is provided, returns only that user's cache key.
        """
        if user_id:
            key = _agent_cache_key(agent_id, user_id)
            return [key] if key in self.agents else []
        prefix = f"{agent_id}:"
        return [
            key
            for key in self.agents
            if key == agent_id or key.startswith(prefix)
        ]

    async def reload_agent(
        self,
        agent_id: str,
        user_id: str | None = None,
    ) -> bool:
        """Reload running workspace instances for ``agent_id``.

        When per-user isolation is enabled, each ``agent_id:user_id`` entry
        is reloaded independently. If ``user_id`` is provided, only that
        user-specific workspace is reloaded.

        Returns:
            bool: True if at least one instance was reloaded
        """
        async with self._lock:
            keys = self._cache_keys_for_agent(agent_id, user_id=user_id)

        if not keys:
            logger.debug(
                "Agent not running, will be loaded on next request: %s",
                agent_id,
            )
            return False

        reloaded = False
        for cache_key in keys:
            if await self._reload_cache_key(cache_key):
                reloaded = True
        return reloaded

    async def _reload_cache_key(self, cache_key: str) -> bool:
        """Reload a single cached workspace by cache key."""
        async with self._lock:
            if cache_key not in self.agents:
                return False
            old_instance = self.agents[cache_key]

        agent_id = old_instance.agent_id
        user_id = old_instance.user_id
        logger.info("Reloading agent (zero-downtime): %s", cache_key)

        try:
            # pylint: disable=protected-access
            old_watcher = old_instance._service_manager.services.get(
                "agent_config_watcher",
            )
            # pylint: enable=protected-access
            if old_watcher is not None:
                await old_watcher.stop()
        except Exception as stop_err:
            logger.warning(
                "Failed to stop old AgentConfigWatcher for %s: %s",
                cache_key,
                stop_err,
            )

        config = load_config()
        if agent_id not in config.agents.profiles:
            logger.error(
                "Agent '%s' not found in configuration during reload",
                agent_id,
            )
            return False

        agent_ref = config.agents.profiles[agent_id]
        new_instance = Workspace(
            agent_id=agent_id,
            workspace_dir=agent_ref.workspace_dir,
            user_id=user_id,
        )

        # pylint: disable=protected-access
        reusable = old_instance._service_manager.get_reusable_services()
        # pylint: enable=protected-access
        if reusable:
            await new_instance.set_reusable_components(reusable)

        try:
            await new_instance.start()
            new_instance.set_manager(self)
        except Exception as e:
            logger.exception(
                "Failed to start new workspace for %s: %s",
                cache_key,
                e,
            )
            try:
                await new_instance.stop()
            except Exception:
                pass
            return False

        async with self._lock:
            if cache_key not in self.agents:
                await new_instance.stop()
                return False
            old_instance = self.agents[cache_key]
            self.agents[cache_key] = new_instance

        await self._graceful_stop_old_instance(old_instance, agent_id)
        return True

    async def cancel_all_cleanup_tasks(self) -> None:
        """Cancel and await all pending delayed cleanup tasks.

        This ensures that any in-progress background cleanups are either
        completed or cleanly cancelled before the manager is torn down.
        Called by stop_all() during shutdown.
        """
        if not self._cleanup_tasks:
            return

        logger.info(
            f"Cancelling {len(self._cleanup_tasks)} pending cleanup "
            f"task(s)...",
        )
        tasks = list(self._cleanup_tasks)
        self._cleanup_tasks.clear()

        for task in tasks:
            if not task.done():
                task.cancel()

        # Await completion of all tasks, collecting exceptions
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("All cleanup tasks cancelled/completed")

    async def stop_all(self):
        """Stop all agent instances.

        Called during application shutdown to clean up resources.
        Cancels any pending delayed cleanup tasks and stops all agents.
        """
        logger.info(f"Stopping all agents ({len(self.agents)} running)...")

        # First, cancel pending cleanup tasks to avoid orphaned instances
        await self.cancel_all_cleanup_tasks()

        # Create list of agent IDs to avoid modifying dict during iteration
        agent_ids = list(self.agents.keys())

        for agent_id in agent_ids:
            try:
                instance = self.agents[agent_id]
                await instance.stop()
                logger.debug(f"Agent stopped: {agent_id}")
            except Exception as e:
                logger.error(f"Error stopping agent {agent_id}: {e}")

        self.agents.clear()
        logger.info("All agents stopped")

    def list_loaded_agents(self) -> list[str]:
        """List currently loaded agent IDs.

        Returns:
            list[str]: List of loaded agent IDs
        """
        return list(self.agents.keys())

    def is_agent_loaded(self, agent_id: str) -> bool:
        """Check if agent is currently loaded.

        Args:
            agent_id: Agent ID to check

        Returns:
            bool: True if agent is loaded and running
        """
        return agent_id in self.agents

    async def preload_agent(self, agent_id: str) -> bool:
        """Preload an agent instance during startup.

        Args:
            agent_id: Agent ID to preload

        Returns:
            bool: True if successfully preloaded, False if failed
        """
        try:
            await self.get_agent(agent_id)
            logger.info(f"Successfully preloaded agent: {agent_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to preload agent {agent_id}: {e}")
            return False

    async def start_all_configured_agents(self) -> dict[str, bool]:
        """Start all enabled agents defined in configuration concurrently.

        Only agents with enabled=True will be started.
        Disabled agents are skipped to save resources.

        Agents are started truly in parallel: get_agent() only holds the
        manager lock briefly for dict checks, releasing it during the slow
        workspace initialization.

        Returns:
            dict[str, bool]: Mapping of agent_id to success status
        """
        config = load_config()
        # Filter only enabled agents
        enabled_agents = {
            agent_id: ref
            for agent_id, ref in config.agents.profiles.items()
            if getattr(ref, "enabled", True)
        }
        agent_ids = list(enabled_agents.keys())

        if not agent_ids:
            logger.warning("No enabled agents configured in config")
            return {}

        total_agents = len(config.agents.profiles)
        disabled_count = total_agents - len(agent_ids)
        logger.debug(
            f"Starting {len(agent_ids)} enabled agent(s) "
            f"({disabled_count} disabled)",
        )

        async def start_single_agent(agent_id: str) -> tuple[str, bool]:
            """Start a single agent with error handling."""
            try:
                logger.debug(f"Starting agent: {agent_id}")
                await self.get_agent(agent_id)
                logger.debug(f"Agent started successfully: {agent_id}")
                return (agent_id, True)
            except Exception as e:
                logger.error(
                    f"Failed to start agent {agent_id}: {e}. "
                    f"Continuing with other agents...",
                )
                return (agent_id, False)

        # Truly parallel: get_agent releases lock during workspace startup
        results = await asyncio.gather(
            *[start_single_agent(agent_id) for agent_id in agent_ids],
            return_exceptions=False,
        )

        # Build result mapping
        result_map = dict(results)
        success_count = sum(1 for success in result_map.values() if success)
        logger.info(
            f"Agent startup complete: {success_count}/{len(agent_ids)} "
            f"agents started successfully, {disabled_count} disabled",
        )

        return result_map

    def __repr__(self) -> str:
        """String representation of manager."""
        loaded = list(self.agents.keys())
        return f"MultiAgentManager(loaded_agents={loaded})"
