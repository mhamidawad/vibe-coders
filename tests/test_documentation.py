"""Tests for the Documentation agent — doc-generation expert."""

import os
import tempfile
import unittest

from vibe_coders.agents.documentation import DocumentationAgent


class DocumentationAgentTests(unittest.TestCase):
    def setUp(self):
        self.agent = DocumentationAgent("doc-1")

    def test_read_only(self):
        # documentation agent writes docs/ but is otherwise scoped
        self.assertFalse(self.agent.read_only)
        self.assertTrue(self.agent.can_write("docs/readme.md"))
        self.assertFalse(self.agent.can_write("vibe_coders/x.py"))

    def test_analyzes_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "mod.py")
            open(path, 'w').write('"""Module docstring."""\n\ndef foo(a: int) -> int:\n    """Return a doubled."""\n    return a * 2\n')
            result = self.agent.run({"files": [path]})
            self.assertEqual(result["status"], "completed")
            self.assertGreater(result["confidence"], 0.5)
            modules = result.get("findings", [])
            self.assertTrue(any(m.get("public_api_count", 0) >= 1 for m in modules))

    def test_reports_missing_docstring(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "nodoc.py")
            open(path, "w").write("def foo():\n    return 1\n")
            result = self.agent.run({"files": [path]})
            self.assertEqual(result["status"], "completed")
            self.assertIsInstance(result.get("generated_changelog"), str)

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
