"""Tests for the Planner agent — task decomposition expert."""

import unittest

from vibe_coders.agents.planner import PlannerAgent


class PlannerAgentTests(unittest.TestCase):
    def setUp(self):
        self.agent = PlannerAgent("plan-1")

    def test_read_only(self):
        self.assertTrue(self.agent.read_only)
        self.assertFalse(self.agent.can_write("vibe_coders/x.py"))

    def test_decomposes_simple_goal(self):
        result = self.agent.run({"goal": "write a config validator and test it"})
        self.assertEqual(result["status"], "completed")
        self.assertGreater(result["confidence"], 0.5)
        subtasks = result.get("findings", [])
        self.assertGreaterEqual(len(subtasks), 1)
        roles = {st["role"] for st in subtasks}
        self.assertIn("implementation", roles)
        self.assertIn("test", roles)

    def test_assigns_dependency_chain(self):
        result = self.agent.run({"goal": "research the codebase then implement a fix"})
        subtasks = result.get("findings", [])
        self.assertTrue(subtasks[0]["depends_on"] == [])
        if len(subtasks) > 1:
            self.assertEqual(subtasks[1]["depends_on"], ["subtask-001"])

    def test_requires_goal(self):
        result = self.agent.run({})
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["confidence"], 0.0)

    def test_role_inference(self):
        self.assertEqual(self.agent._infer_role("write a new module"), "implementation")
        self.assertEqual(self.agent._infer_role("run the test suite"), "test")
        self.assertEqual(self.agent._infer_role("review the architecture"), "review")
        self.assertEqual(self.agent._infer_role("scan for security issues"), "security")
        self.assertEqual(self.agent._infer_role("diagnose the crash"), "debugger")
        self.assertEqual(self.agent._infer_role("write documentation"), "documentation")

    def test_result_structure(self):
        result = self.agent.run({"goal": "implement and test a feature"})
        self.assertIn("status", result)
        self.assertIn("detail", result)
        self.assertIn("confidence", result)
        self.assertIn("evidence", result)
        self.assertIn("findings", result)
        self.assertIn("recommendations", result)
