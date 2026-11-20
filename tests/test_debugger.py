"""Tests for the Debugger agent — root-cause expert."""

import unittest

from vibe_coders.agents.debugger import DebuggerAgent


class DebuggerAgentTests(unittest.TestCase):
    def setUp(self):
        self.agent = DebuggerAgent("dbg-1")

    def test_read_only(self):
        self.assertTrue(self.agent.read_only)
        self.assertFalse(self.agent.can_write("vibe_coders/x.py"))

    def test_detects_modulenotfound(self):
        result = self.agent.run({"error_text": "ModuleNotFoundError: No module named 'foo'"})
        self.assertEqual(result["status"], "completed")
        findings = result.get("findings", [])
        self.assertTrue(any("missing dependency" in f.get("likely_cause", "").lower() for f in findings))
        self.assertGreater(result["confidence"], 0.5)

    def test_detects_syntax_error(self):
        result = self.agent.run({"error_text": "SyntaxError: invalid syntax at line 42"})
        self.assertEqual(result["status"], "completed")
        findings = result.get("findings", [])
        self.assertTrue(any("syntax" in f.get("likely_cause", "").lower() for f in findings))

    def test_abstains_when_no_pattern(self):
        result = self.agent.run({"error_text": "everything is fine here"})
        self.assertEqual(result["status"], "abstained")

    def test_abstains_on_empty(self):
        result = self.agent.run({})
        self.assertEqual(result["status"], "abstained")

    def test_result_structure(self):
        result = self.agent.run({"error_text": "FileNotFoundError: [Errno 2] no such file"})
        for key in ("status", "detail", "confidence", "evidence", "findings", "recommendations"):
            self.assertIn(key, result)
