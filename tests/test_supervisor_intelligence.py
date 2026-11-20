"""Tests for the enhanced Supervisor — intelligent orchestration."""

import unittest

from vibe_coders.supervisor import Supervisor
from vibe_coders.registry import Registry
from vibe_coders.agents.base import BaseAgent


class _EchoAgent(BaseAgent):
    role = "implementation"
    write_allowlist = {"vibe_coders/"}

    def __init__(self, agent_id):
        super().__init__(agent_id)
        self.calls = 0

    def run(self, context):
        self.calls += 1
        return {"status": "completed", "detail": "echo", "confidence": 0.9}


class _FailingAgent(BaseAgent):
    role = "fix"
    write_allowlist = {"tests/"}

    def __init__(self, agent_id, fail_times=1):
        super().__init__(agent_id)
        self.fail_times = fail_times
        self.calls = 0

    def run(self, context):
        self.calls += 1
        if self.calls <= self.fail_times:
            return {"status": "failed", "error": "boom", "confidence": 0.0}
        return {"status": "completed", "detail": "recovered", "confidence": 0.9}


class SupervisorIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.sup = Supervisor(Registry(max_active_agents=3, max_impl_concurrent=2))

    def test_plan_goal(self):
        result = self.sup.plan_goal("write a validator and test it", files=["a.py"])
        self.assertEqual(result["status"], "completed")
        subtasks = result.get("findings", [])
        self.assertGreaterEqual(len(subtasks), 1)

    def test_create_tasks_from_plan(self):
        plan = self.sup.plan_goal("research then implement")
        tasks = self.sup.create_tasks_from_plan(plan)
        self.assertGreaterEqual(len(tasks), 1)
        for t in tasks:
            self.assertIn("planned_role", t.result or {})

    def test_confidence_scored(self):
        agent = _EchoAgent("impl-1")
        task = self.sup.new_task("write module", "implementation", ["vibe_coders/mod.py"])
        self.sup.delegate(task.id, agent)
        result = self.sup.run(task.id, agent, {"path": "vibe_coders/mod.py", "content": "x = 1"})
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["confidence"], 0.9)
        t = self.sup.registry.get_task(task.id)
        self.assertEqual(t.result["confidence"], 0.9)

    def test_strategy_change_after_two_identical_failures(self):
        agent = _FailingAgent("fix-1", fail_times=5)  # always fails
        task = self.sup.new_task("fix something", "fix", ["tests/test_x.py"])
        self.sup.delegate(task.id, agent)
        r1 = self.sup.run(task.id, agent, {"path": "tests/test_x.py", "old": "a", "new": "b"})
        self.assertFalse(r1["strategy_change"])
        self.assertEqual(r1["failure_count"], 1)

        # Re-delegate the same failed task for retry
        self.sup.delegate(task.id, agent)
        r2 = self.sup.run(task.id, agent, {"path": "tests/test_x.py", "old": "a", "new": "b"})
        self.assertTrue(r2["strategy_change"])
        self.assertEqual(r2["failure_count"], 2)

        # A third delegation should be blocked (strategy change required)
        self.assertFalse(self.sup.delegate(task.id, agent))

    def test_strategy_change_not_triggered_on_different_errors(self):
        """Different errors reset the failure counter."""
        agent = _FailingAgent("fix-1", fail_times=1)
        task = self.sup.new_task("fix something", "fix", ["tests/test_x.py"])
        self.sup.delegate(task.id, agent)
        r1 = self.sup.run(task.id, agent, {"path": "tests/test_x.py", "old": "a", "new": "b"})
        self.assertFalse(r1["strategy_change"])

    def test_escalation_on_failure(self):
        agent = _FailingAgent("fix-1", fail_times=1)
        task = self.sup.new_task("fix something", "fix", ["tests/test_x.py"])
        self.sup.delegate(task.id, agent)
        self.sup.run(task.id, agent, {"path": "tests/test_x.py", "old": "a", "new": "b"})
        escalated = self.sup.escalate_on_failure(task.id)
        self.assertIn("debugger", escalated)
        self.assertIn("architecture", escalated)

    def test_report_includes_confidence_and_strategy(self):
        agent = _EchoAgent("impl-1")
        task = self.sup.new_task("write module", "implementation", ["vibe_coders/mod.py"])
        self.sup.delegate(task.id, agent)
        self.sup.run(task.id, agent, {"path": "vibe_coders/mod.py", "content": "x = 1"})
        rep = self.sup.report()
        t = rep["tasks"][task.id]
        self.assertEqual(t["confidence"], 0.9)
        self.assertIn("strategy_change", t)
        self.assertIn("failure_count", t)
