"""Tests for the RAG verifier agent — runs MOe RAG verification commands."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vibe_coders.agents.rag_verifier import RAGVerifierAgent


class RAGVerifierAgentTests(unittest.TestCase):
    def setUp(self):
        self.agent = RAGVerifierAgent("rag-ver-1")

    def test_read_only(self):
        self.assertTrue(self.agent.read_only)
        self.assertFalse(self.agent.can_write("vibe_coders/x.py"))

    def test_requires_rag_repo(self):
        result = self.agent.run({})
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["confidence"], 0.0)

    def test_nonexistent_repo(self):
        result = self.agent.run({"rag_repo": "/nonexistent/path"})
        self.assertEqual(result["status"], "failed")

    @patch("vibe_coders.agents.rag_verifier.RAGVerifierAgent._run_command")
    def test_verification_reports_results(self, mock_run_command):
        # Simulate both suites passing.
        mock_run_command.side_effect = [
            {"command": "unittest", "returncode": 0, "stdout": "OK", "stderr": "", "passed": True},
            {"command": "hallucination", "returncode": 0, "stdout": "OK", "stderr": "", "passed": True},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self.agent.run({"rag_repo": str(root)})
            self.assertEqual(result["status"], "completed")
            self.assertTrue(result.get("all_passed"))
            findings = result.get("findings", [])
            self.assertEqual(len(findings), 2)
            self.assertTrue(all(f["passed"] for f in findings))

    @patch("vibe_coders.agents.rag_verifier.RAGVerifierAgent._run_command")
    def test_verification_reports_failures(self, mock_run_command):
        # Simulate both suites failing (like the real RAG env with missing deps).
        mock_run_command.side_effect = [
            {"command": "unittest", "returncode": 1, "stdout": "", "stderr": "ModuleNotFoundError: lancedb", "passed": False},
            {"command": "hallucination", "returncode": 1, "stdout": "", "stderr": "AssertionError: injected text", "passed": False},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self.agent.run({"rag_repo": str(root)})
            self.assertEqual(result["status"], "completed")
            self.assertFalse(result.get("all_passed"))
            findings = result.get("findings", [])
            self.assertFalse(all(f["passed"] for f in findings))
            # Should include recommendations about pre-existing failures.
            recs = result.get("recommendations", [])
            self.assertTrue(any("Pre-existing failure" in r for r in recs))

    def test_result_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self.agent.run({"rag_repo": str(root)})
            for key in ("status", "detail", "confidence", "evidence", "findings", "recommendations"):
                self.assertIn(key, result)
