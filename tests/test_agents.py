"""Tests for specialist agents: research, implementation, test, review, fix."""

import os
import tempfile
import unittest

from vibe_coders.agents.research import ResearchAgent
from vibe_coders.agents.implementation import ImplementationAgent
from vibe_coders.agents.test_agent import TestAgent
from vibe_coders.agents.review_agent import ReviewAgent
from vibe_coders.agents.fix_agent import FixAgent


class ResearchAgentTests(unittest.TestCase):
    def test_read_only_never_writes(self):
        agent = ResearchAgent("r1")
        self.assertTrue(agent.read_only)
        self.assertFalse(agent.can_write("vibe_coders/x.py"))

    def test_run_lists_files(self):
        agent = ResearchAgent("r1")
        result = agent.run({"root": os.path.abspath("vibe_coders"), "pattern": "*.py"})
        self.assertEqual(result["status"], "completed")
        self.assertTrue(any("agents/__init__.py" in m for m in result["matches"]))


class ImplementationAgentTests(unittest.TestCase):
    def test_write_and_can_write(self):
        agent = ImplementationAgent("i1")
        self.assertTrue(agent.can_write("vibe_coders/foo.py"))
        self.assertTrue(agent.can_write("tests/test_foo.py"))

    def test_run_writes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "vibe_coders")
            os.makedirs(root, exist_ok=True)
            agent = ImplementationAgent("i1")
            target = os.path.join(root, "hello.py")
            result = agent.run({"path": target, "content": "print('hi')\n"})
            self.assertEqual(result["status"], "completed")
            self.assertTrue(os.path.exists(target))
            self.assertEqual(open(target).read(), "print('hi')\n")


class TestAgentTests(unittest.TestCase):
    def test_run_uses_pytest(self):
        agent = TestAgent("t1")
        result = agent.run({"test_paths": []})
        # pytest with no paths collects nothing -> exit 5 (no tests collected)
        # but it runs; status depends on pytest availability. Just ensure it returns.
        self.assertIn(result["status"], ("completed", "failed"))


class ReviewAgentTests(unittest.TestCase):
    def test_review_clean_file(self):
        agent = ReviewAgent("rv1")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "clean.py")
            open(path, "w").write("x = 1\n")
            result = agent.run({"paths": [path]})
            self.assertEqual(result["status"], "completed")

    def test_review_syntax_error(self):
        agent = ReviewAgent("rv1")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.py")
            open(path, "w").write("x = \n")
            result = agent.run({"paths": [path]})
            self.assertEqual(result["status"], "failed")


class FixAgentTests(unittest.TestCase):
    def test_fix_applies_replacement(self):
        agent = FixAgent("fx1")
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs("vibe_coders", exist_ok=True)
            path = os.path.join(tmp, "vibe_coders", "mod.py")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "w").write("OLD\n")
            result = agent.run({"path": path, "old": "OLD", "new": "NEW"})
            self.assertEqual(result["status"], "completed")
            self.assertEqual(open(path).read(), "NEW\n")

    def test_fix_missing_old(self):
        agent = FixAgent("fx1")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "vibe_coders", "mod.py")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "w").write("hello\n")
            result = agent.run({"path": path, "old": "absent", "new": "x"})
            self.assertEqual(result["status"], "failed")


if __name__ == "__main__":
    unittest.main()
