"""Tests for the RAG research agent — read-only MOe RAG codebase analysis."""

import json
import tempfile
import unittest
from pathlib import Path

from vibe_coders.agents.rag_research import RAGResearchAgent


class RAGResearchAgentTests(unittest.TestCase):
    def setUp(self):
        self.agent = RAGResearchAgent("rag-res-1")

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

    def test_research_real_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Create key RAG files.
            (root / "rag").mkdir()
            (root / "rag" / "native.py").write_text(
                '"""Application adapter."""\ndef guarded_fallback(q, e):\n    return {"status": "completed"}\n'
            )
            (root / "configs").mkdir()
            (root / "configs" / "rag-context-slim.json").write_text(
                '{"permissions": [{"action": "tool.use", "resource": "moe-rag_rag_search", "effect": "allow"}]}'
            )
            (root / "configs" / "native-rag.json").write_text("{}")
            (root / "configs" / "supervisor-slim.json").write_text("{}")
            (root / "tasks").mkdir()
            (root / "tasks" / "manifest.json").write_text(
                json.dumps(
                    {
                        "phase": "AUDIT_FIXES_VERIFIED_SUPERVISOR_PENDING",
                        "milestones": {
                            "audit_remediation": "verified",
                            "guarded_fallback": "verified",
                            "least_privilege_agent_profiles": "verified",
                            "supervisor_integration": "pending",
                            "credential_rotation": "pending",
                        },
                        "latest_status": "remediation in progress",
                    }
                )
            )
            (root / "plans").mkdir()
            (root / "plans" / "project-continuity.md").write_text(
                "# OpenCode RAG continuity\nStatus: PARTIAL_INTEGRATION_AUDIT_FIXES_VERIFIED"
            )
            (root / "tests").mkdir()
            (root / "tests" / "test_guarded_fallback.py").write_text("# tests")
            (root / "reports").mkdir()
            (root / "reports" / "guarded-fallback-verification.json").write_text(
                json.dumps({"status": "PASS", "item": 1})
            )
            (root / "reports" / "rag-context-slim-profile.json").write_text(
                json.dumps({"status": "PASS", "item": 2})
            )

            result = self.agent.run({"rag_repo": str(root)})
            self.assertEqual(result["status"], "completed")
            self.assertGreater(result["confidence"], 0.5)

            findings = {f["area"]: f for f in result.get("findings", [])}
            self.assertTrue(findings["guarded_fallback"]["implemented"])
            self.assertTrue(findings["least_privilege_profile"]["implemented"])

            # manifest_summary should be populated.
            ms = result.get("manifest_summary", {})
            self.assertEqual(ms.get("phase"), "AUDIT_FIXES_VERIFIED_SUPERVISOR_PENDING")
            self.assertEqual(ms.get("audit_remediation"), "verified")
            self.assertEqual(ms.get("supervisor_integration"), "pending")

    def test_result_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "rag").mkdir()
            (root / "rag" / "native.py").write_text("x = 1\n")
            result = self.agent.run({"rag_repo": str(root)})
            for key in ("status", "detail", "confidence", "evidence", "findings", "recommendations"):
                self.assertIn(key, result)
