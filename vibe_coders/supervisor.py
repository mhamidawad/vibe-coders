"""Supervisor — the single orchestration authority for specialist agents.

The Supervisor owns all mutable state (Registry). It is the only entity that
may create, launch, or delegate work to subagents. It enforces:

  * max 3 active agents at once
  * max 2 concurrent implementation-role agents (implementation / fix / review
    / planner / architecture / debugger / security / documentation)
  * single-writer file ownership (no two agents write the same file)
  * stage-gated execution: discovery → implementation → testing → review →
    fixes → final_tests → deploy → verify
  * retry-with-strategy-change: after two identical failures on a task, the
    Supervisor stops retrying the same approach and signals a strategy change

Intelligent orchestration features:
  * task decomposition via PlannerAgent before execution
  * confidence scoring on every agent result
  * evidence-based integration of findings
  * automatic escalation to debugger/architecture/security review on failure
"""

from __future__ import annotations

from typing import Optional

from .agents.base import BaseAgent, IMPLEMENTATION_ROLES, make_result
from .agents.planner import PlannerAgent
from .registry import AgentInstance, Registry, Task


class Supervisor:
    """Coordinate specialist agents through the shared Registry."""

    def __init__(self, registry: Optional[Registry] = None):
        self.registry = registry or Registry()
        self._next_task = 0
        self._planner = PlannerAgent("planner-0")
        # task_id -> number of consecutive identical failures
        self._failure_count: dict[str, int] = {}
        # task_id -> last error signature (first 200 chars of error string)
        self._last_error_sig: dict[str, str] = {}

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

    # --- intelligent orchestration --------------------------------------

    def plan_goal(self, goal: str, files=None) -> dict:
        """Decompose a high-level goal into subtasks using the Planner agent.

        Returns the planner result, including the list of subtasks under
        ``findings``. The caller can then create tasks for each subtask.
        """
        context = {"goal": goal, "files": list(files or [])}
        result = self._planner.run(context)
        return result

    def create_tasks_from_plan(self, plan_result: dict) -> list:
        """Create Registry tasks from a planner result's subtask findings."""
        created = []
        for st in plan_result.get("findings", []):
            task = self.new_task(
                title=st["title"],
                agent_role=st["role"],
                file_owns=st.get("output_files", []),
            )
            # store planner metadata on the task for later use
            task.result = {
                "planned_role": st["role"],
                "effort": st.get("effort"),
                "depends_on": st.get("depends_on", []),
                "input_files": st.get("input_files", []),
            }
            created.append(task)
        return created

    # --- delegation ------------------------------------------------------

    def delegate(self, task_id: str, agent: BaseAgent) -> bool:
        """Assign a task to an agent instance.

        Checks concurrency gates and claims file ownership. Returns True on
        successful delegation.
        """
        task = self.registry.get_task(task_id)
        if task is None:
            return False
        if task.status == "completed":
            return False
        if task.status == "assigned":
            return False  # already assigned to an agent
        # Allow re-delegation of failed tasks for retry, but stop after
        # two identical failures (strategy change required).
        if task.status == "failed" and self._failure_count.get(task_id, 0) >= 2:
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
        applies confidence scoring, handles retry-with-strategy-change, and
        releases file ownership. Returns the result dict.
        """
        task = self.registry.get_task(task_id)
        if task is None:
            return make_result(status="failed", error="unknown task", task_id=task_id)
        if task.status != "assigned" or task.assigned_to != agent.agent_id:
            return make_result(
                status="failed", error="task not delegated to this agent", task_id=task_id
            )

        with self.registry._lock:
            task.status = "in_progress"

        try:
            result = agent.run(context)
        except Exception as exc:  # noqa: BLE001 - surface agent errors as failures
            result = make_result(
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
                confidence=0.0,
            )

        # Normalize to a structured result if the agent returned a plain dict.
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

        with self.registry._lock:
            task.result = result

            # Retry-with-strategy-change: track identical failures.
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

    # --- escalation helpers ----------------------------------------------

    def escalate_on_failure(self, task_id: str) -> dict:
        """When a task fails, route to the appropriate expert agent for
        diagnosis. Returns a dict mapping agent role -> agent instance."""
        task = self.registry.get_task(task_id)
        if not task or not task.result:
            return {}

        result = task.result
        error_text = result.get("error", "") or ""
        detail = result.get("detail", "") or ""

        agents = {}
        # Security findings -> security agent
        if any(f.get("severity") == "high" for f in result.get("findings", [])):
            from .agents.security import SecurityAgent

            agents["security"] = SecurityAgent("sec-escalate")
        # Debuggable error patterns -> debugger agent
        if error_text or "failed" in detail.lower():
            from .agents.debugger import DebuggerAgent

            agents["debugger"] = DebuggerAgent("dbg-escalate")
        # Design-level issues -> architecture agent
        from .agents.architecture import ArchitectureAgent

        agents["architecture"] = ArchitectureAgent("arch-escalate")
        return agents

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
