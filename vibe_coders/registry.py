"""Agent registry and task/task-registry data model.

Tracks:
  * which agent roles exist and their profiles (via agents/base.AGENT_PROFILES)
  * the set of live Agent instances and their current load
  * all tasks, their status, and which files each task owns
  * file -> owning agent mapping, to enforce single-writer semantics
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from .agents.base import IMPLEMENTATION_ROLES, ROLES


@dataclass
class Task:
    id: str
    title: str
    agent_role: str
    status: str = "pending"  # pending | assigned | in_progress | completed | failed
    file_owns: List[str] = field(default_factory=list)
    result: Optional[dict] = None
    error: Optional[str] = None
    assigned_to: Optional[str] = None  # agent_id


@dataclass
class AgentInstance:
    agent_id: str
    role: str
    busy: bool = False
    task_id: Optional[str] = None


class Registry:
    """Thread-safe registry of agents, tasks, and file ownership."""

    def __init__(self, max_active_agents: int = 3, max_impl_concurrent: int = 2):
        self.max_active_agents = max_active_agents
        self.max_impl_concurrent = max_impl_concurrent
        self._lock = threading.RLock()

        self.agents: Dict[str, AgentInstance] = {}
        self.tasks: Dict[str, Task] = {}
        # file path -> agent_id that currently owns (is writing) it
        self.file_owner: Dict[str, str] = {}
        # agent_id -> set of files it currently owns
        self.agent_files: Dict[str, Set[str]] = {}

    # --- agent lifecycle -------------------------------------------------

    def register_agent(self, agent_id: str, role: str) -> bool:
        with self._lock:
            if role not in ROLES:
                return False
            if agent_id in self.agents:
                return False
            self.agents[agent_id] = AgentInstance(agent_id=agent_id, role=role)
            return True

    def unregister_agent(self, agent_id: str) -> bool:
        with self._lock:
            inst = self.agents.pop(agent_id, None)
            if inst is None:
                return False
            # release any files this agent owned
            for path in list(self.agent_files.get(agent_id, set())):
                self.file_owner.pop(path, None)
            self.agent_files.pop(agent_id, None)
            return True

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for a in self.agents.values() if a.busy)

    def impl_busy_count(self) -> int:
        with self._lock:
            return sum(
                1
                for a in self.agents.values()
                if a.busy and a.role in IMPLEMENTATION_ROLES
            )

    def available_agent(self, role: str) -> Optional[str]:
        """Return an idle agent_id of the given role, or None."""
        with self._lock:
            for aid, inst in self.agents.items():
                if inst.role == role and not inst.busy:
                    return aid
            return None

    # --- task lifecycle --------------------------------------------------

    def add_task(self, task: Task) -> None:
        with self._lock:
            self.tasks[task.id] = task

    def get_task(self, task_id: str) -> Optional[Task]:
        with self._lock:
            return self.tasks.get(task_id)

    def list_tasks(self) -> List[Task]:
        with self._lock:
            return list(self.tasks.values())

    # --- file ownership (single-writer) ----------------------------------

    def claim_files(self, agent_id: str, paths: List[str]) -> bool:
        """Atomically claim file paths for an agent. Fails if any path is
        already owned by a different agent."""
        with self._lock:
            for path in paths:
                owner = self.file_owner.get(path)
                if owner is not None and owner != agent_id:
                    return False
            for path in paths:
                self.file_owner[path] = agent_id
                self.agent_files.setdefault(agent_id, set()).add(path)
            return True

    def release_files(self, agent_id: str) -> None:
        with self._lock:
            for path in list(self.agent_files.get(agent_id, set())):
                self.file_owner.pop(path, None)
            self.agent_files.pop(agent_id, None)

    def owner_of(self, path: str) -> Optional[str]:
        with self._lock:
            return self.file_owner.get(path)

    # --- concurrency gates ----------------------------------------------

    def can_start(self, role: str) -> bool:
        """Whether a new agent of the given role may start work right now."""
        with self._lock:
            if self.active_count() >= self.max_active_agents:
                return False
            if role in IMPLEMENTATION_ROLES and self.impl_busy_count() >= self.max_impl_concurrent:
                return False
            return True
