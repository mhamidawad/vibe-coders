"""Tests for the Registry: agent lifecycle, task lifecycle, file ownership,
and concurrency gates."""

import unittest

from vibe_coders.registry import Registry
from vibe_coders.agents.base import IMPLEMENTATION_ROLES


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.reg = Registry(max_active_agents=3, max_impl_concurrent=2)

    def test_register_and_active_count(self):
        self.assertTrue(self.reg.register_agent("a1", "research"))
        self.assertTrue(self.reg.register_agent("a2", "implementation"))
        self.assertEqual(self.reg.active_count(), 0)  # none busy yet

    def test_can_start_respects_max_active(self):
        self.reg.register_agent("a1", "research")
        self.reg.register_agent("a2", "implementation")
        self.reg.register_agent("a3", "fix")
        # mark all three busy
        for aid in ("a1", "a2", "a3"):
            inst = self.reg.agents[aid]
            inst.busy = True
        self.assertFalse(self.reg.can_start("research"))

    def test_can_start_respects_impl_concurrency(self):
        self.reg.register_agent("i1", "implementation")
        self.reg.register_agent("i2", "implementation")
        self.reg.register_agent("i3", "implementation")
        for aid in ("i1", "i2"):
            self.reg.agents[aid].busy = True
        # third impl agent cannot start (max 2 impl concurrent)
        self.assertFalse(self.reg.can_start("implementation"))
        # but a non-impl role could (active count still under 3)
        self.assertTrue(self.reg.can_start("research"))

    def test_task_add_and_get(self):
        self.reg.add_task(TaskStub("t-1", "do thing", "implementation"))
        t = self.reg.get_task("t-1")
        self.assertIsNotNone(t)
        self.assertEqual(t.title, "do thing")
        self.assertEqual(t.status, "pending")

    def test_claim_files_single_writer(self):
        self.reg.register_agent("w1", "implementation")
        self.reg.register_agent("w2", "implementation")
        self.assertTrue(self.reg.claim_files("w1", ["vibe_coders/a.py"]))
        # second agent cannot claim the same file
        self.assertFalse(self.reg.claim_files("w2", ["vibe_coders/a.py"]))
        # different file is fine
        self.assertTrue(self.reg.claim_files("w2", ["vibe_coders/b.py"]))
        self.assertEqual(self.reg.owner_of("vibe_coders/a.py"), "w1")

    def test_release_files(self):
        self.reg.register_agent("w1", "implementation")
        self.reg.claim_files("w1", ["vibe_coders/a.py"])
        self.reg.release_files("w1")
        self.assertIsNone(self.reg.owner_of("vibe_coders/a.py"))

    def test_unregister_agent_releases_files(self):
        self.reg.register_agent("w1", "implementation")
        self.reg.claim_files("w1", ["vibe_coders/a.py"])
        self.reg.unregister_agent("w1")
        self.assertIsNone(self.reg.owner_of("vibe_coders/a.py"))

    def test_available_agent(self):
        self.reg.register_agent("r1", "research")
        self.reg.register_agent("r2", "research")
        self.reg.agents["r1"].busy = True
        self.assertEqual(self.reg.available_agent("research"), "r2")


class TaskStub:
    def __init__(self, id, title, agent_role):
        self.id = id
        self.title = title
        self.agent_role = agent_role
        self.status = "pending"
        self.file_owns = []
        self.result = None
        self.error = None
        self.assigned_to = None


class ConcurrencyLimitsTests(unittest.TestCase):
    def test_roles_constant(self):
        self.assertIn("implementation", IMPLEMENTATION_ROLES)
        self.assertIn("fix", IMPLEMENTATION_ROLES)
        self.assertIn("review", IMPLEMENTATION_ROLES)
        self.assertNotIn("research", IMPLEMENTATION_ROLES)
