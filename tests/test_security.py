"""Tests for the Security agent — security review expert."""

import os
import tempfile
import unittest

from vibe_coders.agents.security import SecurityAgent


class SecurityAgentTests(unittest.TestCase):
    def setUp(self):
        self.agent = SecurityAgent("sec-1")

    def test_read_only(self):
        self.assertTrue(self.agent.read_only)
        self.assertFalse(self.agent.can_write("vibe_coders/x.py"))

    def test_detects_hardcoded_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.py")
            open(path, "w").write('API_KEY = "sk-1234567890abcdef"\n')
            result = self.agent.run({"files": [path]})
            self.assertEqual(result["status"], "failed")  # high severity -> failed
            findings = result.get("findings", [])
            self.assertTrue(any("API key" in f.get("issue", "") for f in findings))

    def test_detects_eval(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.py")
            open(path, "w").write("eval(user_input)\n")
            result = self.agent.run({"files": [path]})
            findings = result.get("findings", [])
            self.assertTrue(any("eval()" in f.get("issue", "") for f in findings))

    def test_detects_shell_true(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "run.py")
            open(path, "w").write("subprocess.run(cmd, shell=True)\n")
            result = self.agent.run({"files": [path]})
            findings = result.get("findings", [])
            self.assertTrue(any("shell" in f.get("issue", "").lower() for f in findings))

    def test_clean_code_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "clean.py")
            open(path, "w").write("x = 1\ndef foo():\n    return 2\n")
            result = self.agent.run({"files": [path]})
            self.assertEqual(result["status"], "completed")

    def test_no_files_abstains(self):
        result = self.agent.run({"files": [], "roots": []})
        self.assertEqual(result["status"], "abstained")

    def test_result_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "mod.py")
            open(path, "w").write("x = 1\n")
            result = self.agent.run({"files": [path]})
            for key in ("status", "detail", "confidence", "evidence", "findings", "recommendations"):
                self.assertIn(key, result)
