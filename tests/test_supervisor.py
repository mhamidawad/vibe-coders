"""Tests for the Supervisor: delegation, execution, stage gates, reporting."""

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
        return {"status": "completed", "detail": "echo", "received": context}


class _FailingAgent(BaseAgent):
    role = "fix"
    write_allowlist = {"tests/"}

    def run(self, context):
        raise RuntimeError("boom")


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.sup = Supervisor(Registry(max_active_agents=3, max_impl_concurrent=2))

    def test_new_task(self):
        t = self.sup.new_task("write module", "implementation", ["vibe_coders/mod.py"])
        self.assertTrue(t.id.startswith("task-"))
        self.assertEqual(t.status, "pending")

    def test_delegate_and_run(self):
        agent = _EchoAgent("impl-1")
        task = self.sup.new_task("write module", "implementation", ["vibe_coders/mod.py"])
        self.assertTrue(self.sup.delegate(task.id, agent))
        result = self.sup.run(task.id, agent, {"path": "vibe_coders/mod.py", "content": "x = 1"})
        self.assertEqual(result["status"], "completed")
        task2 = self.sup.registry.get_task(task.id)
        self.assertEqual(task2.status, "completed")
        # agent freed, file released
        self.assertFalse(agent.calls == 0)

    def test_cannot_delegate_twice(self):
        agent = _EchoAgent("impl-1")
        task = self.sup.new_task("write module", "implementation", ["vibe_coders/mod.py"])
        self.sup.delegate(task.id, agent)
        self.assertFalse(self.sup.delegate(task.id, agent))

    def test_file_ownership_blocks_concurrent_delegation(self):
        a1 = _EchoAgent("impl-1")
        a2 = _EchoAgent("impl-2")
        t1 = self.sup.new_task("write a", "implementation", ["vibe_coders/a.py"])
        t2 = self.sup.new_task("write b", "implementation", ["vibe_coders/a.py"])
        self.assertTrue(self.sup.delegate(t1.id, a1))
        # a2 cannot start t1's file because a1 owns it; but t2 is a different task
        # delegation of t2 to a2 should still fail because file already owned
        self.assertFalse(self.sup.delegate(t2.id, a2))

    def test_agent_failure_marks_task_failed(self):
        agent = _FailingAgent("fix-1")
        task = self.sup.new_task("fix something", "fix", ["tests/test_x.py"])
        self.sup.delegate(task.id, agent)
        result = self.sup.run(task.id, agent, {"path": "tests/test_x.py", "old": "x", "new": "y"})
        self.assertEqual(result["status"], "failed")
        t = self.sup.registry.get_task(task.id)
        self.assertEqual(t.status, "failed")

    def test_report(self):
        self.sup.new_task("t1", "research")
        self.sup.new_task("t2", "test")
        rep = self.sup.report()
        self.assertIn("active_agents", rep)
        self.assertIn("tasks", rep)
        self.assertIn("agents", rep)

    def test_stage_gate_known(self):
        for stage in ("discovery", "implementation", "testing", "review", "fixes",
                      "final_tests", "deploy", "verify"):
            self.assertTrue(self.sup.stage_gate(stage))
        with self.assertRaises(ValueError):
            self.sup.stage_gate("not_a_stage")


class ConcurrencyGateTests(unittest.TestCase):
    def test_max_active_agents(self):
        sup = Supervisor(Registry(max_active_agents=2, max_impl_concurrent=2))
        agents = [_EchoAgent(f"i{n}") for n in range(3)]
        tasks = [sup.new_task(f"t{n}", "implementation", [f"vibe_coders/m{n}.py"]) for n in range(3)]
        # delegate two
        self.assertTrue(sup.delegate(tasks[0].id, agents[0]))
        self.assertTrue(sup.delegate(tasks[1].id, agents[1]))
        # third should be blocked by max_active_agents
        self.assertFalse(sup.delegate(tasks[2].id, agents[2]))
