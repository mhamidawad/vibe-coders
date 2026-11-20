"""Supervisor — the single orchestration authority for specialist agents.

The Supervisor owns all mutable state (Registry). It is the only entity that
may create, launch, or delegate work to subagents. It enforces:

  * max 3 active agents at once
  * max 2 concurrent implementation-role agents (implementation / fix / review)
  * single-writer file ownership (no two agents write the same file)
  * stage-gated execution: a task only runs when its stage prerequisites are met

Specialist agents are passive: they receive a context dict and return a result
dict. The Supervisor handles assignment, concurrency, file ownership, and
integration of results.
"""

from __future__ import annotations

from typing import Optional

from .agents.base import BaseAgent
from .registry import AgentInstance, Registry, Task


class Supervisor:
    """Coordinate specialist agents through the shared Registry."""

    def __init__(self, registry: Optional[Registry] = None):
        self.registry = registry or Registry()
        self._next_task = 0

    # --- task creation ---------------------------------------------------

    def new_task(self, title: str, agent_role: str, file_owns=None) -> Task:
        """Create and register a new task. Returns the Task."""
        with self.registry._lock:
            self._next_task += 1
            task = Task(
                id=f"task-{self._next_task:04d}",
                title=title,
                agent_role=agent_role,
                file_owns=list(file_owns or []),
            )
        self.registry.add_task(task)
        return task

    # --- delegation ------------------------------------------------------

    def delegate(self, task_id: str, agent: BaseAgent) -> bool:
        """Assign a task to an agent instance.

        Checks concurrency gates and claims file ownership. Returns True on
        successful delegation.
        """
        task = self.registry.get_task(task_id)
        if task is None:
            return False
        if task.status != "pending":
            return False
        if agent.role != task.agent_role:
            return False

        with self.registry._lock:
            # concurrency gates
            if not self.registry.can_start(agent.role):
                return False
            # register agent instance if not already
            if agent.agent_id not in self.registry.agents:
                self.registry.register_agent(agent.agent_id, agent.role)
            # claim files (single-writer)
            if not self.registry.claim_files(agent.agent_id, task.file_owns):
                return False

            task.status = "assigned"
            task.assigned_to = agent.agent_id
            inst = self.registry.agents[agent.agent_id]
            inst.busy = True
            inst.task_id = task_id
        return True

    def run(self, task_id: str, agent: BaseAgent, context: dict) -> dict:
        """Execute one delegated task end-to-end.

        Marks the task in_progress, calls agent.run(), integrates the result,
        releases file ownership, and marks the agent idle. Returns the result
        dict (with status merged into the task).
        """
        task = self.registry.get_task(task_id)
        if task is None:
            return {"status": "failed", "error": "unknown task", "task_id": task_id}
        if task.status != "assigned" or task.assigned_to != agent.agent_id:
            return {"status": "failed", "error": "task not delegated to this agent", "task_id": task_id}

        with self.registry._lock:
            task.status = "in_progress"

        try:
            result = agent.run(context)
        except Exception as exc:  # noqa: BLE001 - surface agent errors as failures
            result = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}

        result_status = result.get("status", "failed")
        with self.registry._lock:
            task.result = result
            task.status = "completed" if result_status == "completed" else "failed"
            if not result_status == "completed":
                task.error = result.get("error")
            # release files and free the agent
            self.registry.release_files(agent.agent_id)
            inst = self.registry.agents.get(agent.agent_id)
            if inst is not None:
                inst.busy = False
                inst.task_id = None

        return result

    # --- stage gate ------------------------------------------------------

    def stage_gate(self, stage: str) -> bool:
        """Placeholder for stage-gate validation. Returns True by default.

        Stages: discovery, implementation, testing, review, fixes,
        final_tests, deploy, verify.
        """
        allowed = {
            "discovery", "implementation", "testing", "review", "fixes",
            "final_tests", "deploy", "verify",
        }
        if stage not in allowed:
            raise ValueError(f"unknown stage: {stage}")
        return True

    # --- reporting -------------------------------------------------------

    def report(self) -> dict:
        with self.registry._lock:
            tasks = [t for t in self.registry.tasks.values()]
            agents = [a for a in self.registry.agents.values()]
        return {
            "active_agents": self.registry.active_count(),
            "impl_busy": self.registry.impl_busy_count(),
            "max_active_agents": self.registry.max_active_agents,
            "max_impl_concurrent": self.registry.max_impl_concurrent,
            "tasks": {
                t.id: {
                    "title": t.title,
                    "role": t.agent_role,
                    "status": t.status,
                    "assigned_to": t.assigned_to,
                    "file_owns": list(t.file_owns),
                    "error": t.error,
                }
                for t in tasks
            },
            "agents": {
                a.agent_id: {"role": a.role, "busy": a.busy, "task_id": a.task_id}
                for a in agents
            },
        }
