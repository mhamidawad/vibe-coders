"""Tests for the Architecture agent — system-design expert."""

import os
import tempfile
import unittest

from vibe_coders.agents.architecture import ArchitectureAgent


class ArchitectureAgentTests(unittest.TestCase):
    def setUp(self):
        self.agent = ArchitectureAgent("arch-1")

    def test_read_only(self):
        self.assertTrue(self.agent.read_only)
        self.assertFalse(self.agent.can_write("vibe_coders/x.py"))

    def test_analyzes_clean_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "clean.py")
            open(path, "w").write("x = 1\ndef foo():\n    return 2\n")
            result = self.agent.run({"files": [path]})
            self.assertEqual(result["status"], "completed")
            self.assertGreater(result["confidence"], 0.5)
            self.assertEqual(result["detail"].count("module(s)"), 1)

    def test_flags_god_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "god.py")
            # 25 public functions = exceeds GOD_MODULE_THRESHOLD (20)
            lines = ["def f%d():\n    return %d\n" % (i, i) for i in range(25)]
            open(path, "w").write("\n".join(lines))
            result = self.agent.run({"files": [path]})
            findings = result.get("findings", [])
            god = [f for f in findings if "god module" in f.get("issue", "")]
            self.assertTrue(god, f"expected god module finding, got: {findings}")

    def test_parse_error_handled(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.py")
            open(path, "w").write("def (\n")
            result = self.agent.run({"files": [path]})
            self.assertEqual(result["status"], "failed")

    def test_no_files_abstains(self):
        result = self.agent.run({"files": [], "roots": []})
        self.assertEqual(result["status"], "abstained")
        self.assertEqual(result["confidence"], 0.0)

    def test_result_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "mod.py")
            open(path, "w").write("x = 1\n")
            result = self.agent.run({"files": [path]})
            for key in ("status", "detail", "confidence", "evidence", "findings", "recommendations"):
                self.assertIn(key, result)
