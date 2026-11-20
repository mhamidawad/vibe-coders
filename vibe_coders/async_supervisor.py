"""Async Supervisor — concurrent multi-agent orchestration with asyncio.

Extends the synchronous Supervisor with:
  * async agent run methods (agents may define ``async_run``)
  * concurrent execution of independent tasks via asyncio.gather
  * semaphore-based concurrency limits (max active / max impl-role)
  * non-blocking delegation with async task lifecycle

All safety constraints (single-writer ownership, stage gates,
retry-with-strategy-change) carry over unchanged.
"""

from __future__ import annotations

import asyncio
from typing import Optional, Sequence

from .agents.base import BaseAgent, IMPLEMENTATION_ROLES, make_result
from .agents.planner import PlannerAgent
from .registry import AgentInstance, Registry, Task


class AsyncSupervisor:
    """Async-capable coordinator for specialist agents."""

    def __init__(
        self,
        registry: Optional[Registry] = None,
        max_active_agents: int = 3,
        max_impl_concurrent: int = 2,
    ):
        self.registry = registry or Registry(
            max_active_agents=max_active_agents,
            max_impl_concurrent=max_impl_concurrent,
        )
        self._next_task = 0
        self._planner = PlannerAgent("planner-0")
        # task_id -> consecutive identical failure count
        self._failure_count: dict[str, int] = {}
        # task_id -> last error signature
        self._last_error_sig: dict[str, str] = {}
        # semaphore gating active agent count
        self._active_semaphore = asyncio.Semaphore(max_active_agents)
        # semaphore gating impl-role concurrency
        self._impl_semaphore = asyncio.Semaphore(max_impl_concurrent)
        # lock for shared state mutation
        self._lock = asyncio.Lock()

    # --- task creation ---------------------------------------------------

    def new_task(self, title: str, agent_role: str, file_owns=None) -> Task:
        """Create and register a new task (sync). Returns the Task."""
        with self.registry._lock:  # type: ignore[attr-defined]
            self._next_task += 1
            task = Task(
                id=f"task-{self._next_task:04d}",
                title=title,
                agent_role=agent_role,
                file_owns=list(file_owns or []),
            )
        self.registry.add_task(task)
        return task

    async def plan_goal(self, goal: str, files=None) -> dict:
        """Decompose a high-level goal into subtasks (async)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self._planner.run({"goal": goal, "files": list(files or [])})
        )

    async def create_tasks_from_plan(self, plan_result: dict) -> list:
        """Create Registry tasks from a planner result (async)."""
        created = []
        for st in plan_result.get("findings", []):
            task = self.new_task(
                title=st["title"],
                agent_role=st["role"],
                file_owns=st.get("output_files", []),
            )
            task.result = {
                "planned_role": st["role"],
                "effort": st.get("effort"),
                "depends_on": st.get("depends_on", []),
                "input_files": st.get("input_files", []),
            }
            created.append(task)
        return created

    # --- delegation ------------------------------------------------------

    def _can_delegate_sync(self, task: Task, agent: BaseAgent) -> bool:
        if task.status == "completed":
            return False
        if task.status == "assigned":
            return False
        if task.status == "failed" and self._failure_count.get(task.id, 0) >= 2:
            return False
        if agent.role != task.agent_role:
            return False
        return True

    async def delegate(self, task_id: str, agent: BaseAgent) -> bool:
        """Assign a task to an agent instance (async)."""
        async with self._lock:
            task = self.registry.get_task(task_id)
            if task is None:
                return False
            if not self._can_delegate_sync(task, agent):
                return False
            # concurrency: acquire semaphores non-blocking to test availability
            if self._active_semaphore.locked() and self.registry.active_count() >= self.registry.max_active_agents:
                return False
            if agent.role in IMPLEMENTATION_ROLES:
                if self._impl_semaphore.locked() and self.registry.impl_busy_count() >= self.registry.max_impl_concurrent:
                    return False
            if agent.agent_id not in self.registry.agents:
                self.registry.register_agent(agent.agent_id, agent.role)
            if not self.registry.claim_files(agent.agent_id, task.file_owns):
                return False
            task.status = "assigned"
            task.assigned_to = agent.agent_id
            inst = self.registry.agents[agent.agent_id]
            inst.busy = True
            inst.task_id = task_id
        return True

    # --- execution -------------------------------------------------------

    async def _run_agent(self, agent: BaseAgent, context: dict) -> dict:
        """Run an agent, preferring async_run if available."""
        if hasattr(agent, "async_run") and asyncio.iscoroutinefunction(agent.async_run):  # type: ignore[attr-defined]
            return await agent.async_run(context)  # type: ignore[attr-defined]
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: agent.run(context))

    async def run(self, task_id: str, agent: BaseAgent, context: dict) -> dict:
        """Execute one delegated task end-to-end (async).

        Acquires concurrency semaphores for the duration of execution.
        """
        task = self.registry.get_task(task_id)
        if task is None:
            return make_result(status="failed", error="unknown task", task_id=task_id)
        if task.status != "assigned" or task.assigned_to != agent.agent_id:
            return make_result(
                status="failed", error="task not delegated to this agent", task_id=task_id
            )

        # Choose the right semaphore based on role.
        sem = self._impl_semaphore if agent.role in IMPLEMENTATION_ROLES else self._active_semaphore

        async with sem:
            async with self._lock:
                task.status = "in_progress"

            try:
                result = await self._run_agent(agent, context)
            except Exception as exc:  # noqa: BLE001
                result = make_result(
                    status="failed",
                    error=f"{type(exc).__name__}: {exc}",
                    confidence=0.0,
                )

            if not isinstance(result, dict):
                result = make_result(status="failed", error="agent returned non-dict", confidence=0.0)
            result.setdefault("status", "failed")
            result.setdefault("detail", "")
            result.setdefault("confidence", 0.5)
            result.setdefault("evidence", [])
            result.setdefault("findings", [])
            result.setdefault("recommendations", [])

            result_status = result.get("status", "failed")
            error_sig = str(result.get("error", ""))[:200]

            async with self._lock:
                task.result = result

                # Retry-with-strategy-change.
                prev_sig = self._last_error_sig.get(task_id)
                if result_status == "failed":
                    if prev_sig == error_sig and error_sig:
                        self._failure_count[task_id] = self._failure_count.get(task_id, 0) + 1
                    else:
                        self._failure_count[task_id] = 1
                        self._last_error_sig[task_id] = error_sig
                else:
                    self._failure_count[task_id] = 0
                    self._last_error_sig.pop(task_id, None)

                strategy_change = self._failure_count.get(task_id, 0) >= 2
                task.status = "completed" if result_status == "completed" else "failed"
                if result_status != "completed":
                    task.error = result.get("error")
                task.result["strategy_change"] = strategy_change
                task.result["failure_count"] = self._failure_count.get(task_id, 0)

                # Release files and free agent.
                self.registry.release_files(agent.agent_id)
                inst = self.registry.agents.get(agent.agent_id)
                if inst is not None:
                    inst.busy = False
                    inst.task_id = None

        return result

    # --- batch execution -------------------------------------------------

    async def run_concurrent(
        self, tasks_agents: Sequence[tuple]
    ) -> list:
        """Run multiple (task, agent, context) tuples concurrently.

        Each element is (task_id, agent, context). Returns results in order.
        Concurrency limits are enforced by semaphores.
        """

        async def _one(tid, ag, ctx):
            return await self.run(tid, ag, ctx)

        return await asyncio.gather(*[_one(tid, ag, ctx) for tid, ag, ctx in tasks_agents])

    # --- escalation ------------------------------------------------------

    def escalate_on_failure(self, task_id: str) -> dict:
        """Route a failed task to expert agents for diagnosis (sync)."""
        task = self.registry.get_task(task_id)
        if not task or not task.result:
            return {}

        result = task.result
        error_text = result.get("error", "") or ""
        agents = {}
        if any(f.get("severity") == "high" for f in result.get("findings", [])):
            from .agents.security import SecurityAgent

            agents["security"] = SecurityAgent("sec-escalate")
        if error_text or "failed" in result.get("detail", "").lower():
            from .agents.debugger import DebuggerAgent

            agents["debugger"] = DebuggerAgent("dbg-escalate")
        from .agents.architecture import ArchitectureAgent

        agents["architecture"] = ArchitectureAgent("arch-escalate")
        return agents

    # --- reporting -------------------------------------------------------

    def report(self) -> dict:
        with self.registry._lock:  # type: ignore[attr-defined]
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
                    "confidence": (t.result or {}).get("confidence"),
                    "strategy_change": (t.result or {}).get("strategy_change", False),
                    "failure_count": (t.result or {}).get("failure_count", 0),
                }
                for t in tasks
            },
            "agents": {
                a.agent_id: {"role": a.role, "busy": a.busy, "task_id": a.task_id}
                for a in agents
            },
        }
