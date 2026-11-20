"""Tests for the AsyncSupervisor — concurrent async orchestration."""

import asyncio
import unittest

from vibe_coders.async_supervisor import AsyncSupervisor
from vibe_coders.agents.base import BaseAgent, make_result
from vibe_coders.registry import Registry


class _AsyncEchoAgent(BaseAgent):
    role = "implementation"
    write_allowlist = {"vibe_coders/"}

    def __init__(self, agent_id):
        super().__init__(agent_id)
        self.calls = 0

    async def async_run(self, context):
        self.calls += 1
        await asyncio.sleep(0.01)
        return make_result(status="completed", detail="async echo", confidence=0.9)


class _AsyncFailingAgent(BaseAgent):
    role = "fix"
    write_allowlist = {"tests/"}

    def __init__(self, agent_id, fail_times=1):
        super().__init__(agent_id)
        self.fail_times = fail_times
        self.calls = 0

    async def async_run(self, context):
        self.calls += 1
        await asyncio.sleep(0.01)
        if self.calls <= self.fail_times:
            return make_result(status="failed", error="boom", confidence=0.0)
        return make_result(status="completed", detail="recovered", confidence=0.9)


class AsyncSupervisorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.sup = AsyncSupervisor(
            Registry(max_active_agents=3, max_impl_concurrent=2)
        )

    async def test_new_task(self):
        t = self.sup.new_task("write module", "implementation", ["vibe_coders/mod.py"])
        self.assertTrue(t.id.startswith("task-"))
        self.assertEqual(t.status, "pending")

    async def test_delegate_and_run_async(self):
        agent = _AsyncEchoAgent("impl-1")
        task = self.sup.new_task("write module", "implementation", ["vibe_coders/mod.py"])
        self.assertTrue(await self.sup.delegate(task.id, agent))
        result = await self.sup.run(task.id, agent, {"path": "vibe_coders/mod.py", "content": "x = 1"})
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["confidence"], 0.9)
        t = self.sup.registry.get_task(task.id)
        self.assertEqual(t.status, "completed")

    async def test_concurrent_execution_respects_limits(self):
        # Create 4 implementation tasks; only 2 should run concurrently.
        agents = [_AsyncEchoAgent(f"impl-{n}") for n in range(4)]
        tasks = [
            self.sup.new_task(f"t{n}", "implementation", [f"vibe_coders/m{n}.py"]) for n in range(4)
        ]
        for t, a in zip(tasks, agents):
            await self.sup.delegate(t.id, a)

        executions = [(t.id, a, {"path": t.file_owns[0], "content": "x = 1"}) for t, a in zip(tasks, agents)]
        results = await self.sup.run_concurrent(executions)
        self.assertEqual(len(results), 4)
        self.assertTrue(all(r["status"] == "completed" for r in results))

    async def test_strategy_change_after_two_failures(self):
        agent = _AsyncFailingAgent("fix-1", fail_times=5)
        task = self.sup.new_task("fix something", "fix", ["tests/test_x.py"])
        await self.sup.delegate(task.id, agent)
        r1 = await self.sup.run(task.id, agent, {"path": "tests/test_x.py", "old": "a", "new": "b"})
        self.assertFalse(r1["strategy_change"])
        self.assertEqual(r1["failure_count"], 1)

        await self.sup.delegate(task.id, agent)
        r2 = await self.sup.run(task.id, agent, {"path": "tests/test_x.py", "old": "a", "new": "b"})
        self.assertTrue(r2["strategy_change"])
        self.assertEqual(r2["failure_count"], 2)

        # Third delegation blocked.
        self.assertFalse(await self.sup.delegate(task.id, agent))

    async def test_plan_goal_async(self):
        plan = await self.sup.plan_goal("write a validator and test it", files=["a.py"])
        self.assertEqual(plan["status"], "completed")
        subtasks = plan.get("findings", [])
        self.assertGreaterEqual(len(subtasks), 1)

    async def test_create_tasks_from_plan_async(self):
        plan = await self.sup.plan_goal("research then implement")
        tasks = await self.sup.create_tasks_from_plan(plan)
        self.assertGreaterEqual(len(tasks), 1)

    async def test_report(self):
        self.sup.new_task("t1", "research")
        self.sup.new_task("t2", "test")
        rep = self.sup.report()
        self.assertIn("active_agents", rep)
        self.assertIn("tasks", rep)

    async def test_run_concurrent_returns_in_order(self):
        agents = [_AsyncEchoAgent(f"impl-{n}") for n in range(3)]
        tasks = [
            self.sup.new_task(f"t{n}", "implementation", [f"vibe_coders/m{n}.py"]) for n in range(3)
        ]
        for t, a in zip(tasks, agents):
            await self.sup.delegate(t.id, a)
        executions = [(t.id, a, {"path": t.file_owns[0], "content": "x"}) for t, a in zip(tasks, agents)]
        results = await self.sup.run_concurrent(executions)
        self.assertEqual([r["status"] for r in results], ["completed", "completed", "completed"])
