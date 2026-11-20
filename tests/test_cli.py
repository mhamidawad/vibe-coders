"""Tests for the CLI entry point."""

import asyncio
import unittest
from unittest.mock import patch

from vibe_coders.cli import main, run_goal, run_rag_integration, _agent_for, _file_owns_for
from vibe_coders.agents.implementation import ImplementationAgent
from vibe_coders.agents.test_agent import TestAgent
from vibe_coders.agents.review_agent import ReviewAgent
from vibe_coders.agents.rag_research import RAGResearchAgent
from vibe_coders.agents.rag_verifier import RAGVerifierAgent


class CLIAgentMappingTests(unittest.TestCase):
    def test_agent_for_roles(self):
        self.assertIsInstance(_agent_for("implementation", "impl-1"), ImplementationAgent)
        self.assertIsInstance(_agent_for("test", "test-1"), TestAgent)
        self.assertIsInstance(_agent_for("review", "rev-1"), ReviewAgent)

    def test_file_owns_for(self):
        self.assertEqual(_file_owns_for("implementation", {}), ["vibe_coders/module.py"])
        self.assertEqual(_file_owns_for("fix", {}), ["tests/test_module.py"])
        self.assertEqual(_file_owns_for("documentation", {}), ["docs/module.md"])
        # explicit output_files take precedence
        self.assertEqual(_file_owns_for("implementation", {"output_files": ["custom.py"]}), ["custom.py"])

    def test_file_owns_for_unknown_role(self):
        self.assertEqual(_file_owns_for("security", {}), [])


class CLIMainTests(unittest.TestCase):
    def test_main_requires_goal(self):
        with self.assertRaises(SystemExit) as ctx:
            main([])
        self.assertEqual(ctx.exception.code, 2)  # argparse error exit code

    @patch("vibe_coders.cli.run_goal")
    @patch("vibe_coders.cli.asyncio.run")
    def test_main_runs_goal(self, mock_asyncio_run, mock_run_goal):
        mock_run_goal.side_effect = lambda **kwargs: asyncio.sleep(0)
        mock_asyncio_run.side_effect = lambda coro: {
            "active_agents": 0, "impl_busy": 0,
            "max_active_agents": 3, "max_impl_concurrent": 2,
            "tasks": {}, "agents": {},
        }
        code = main(["--goal", "add a validator", "--json"])
        self.assertEqual(code, 0)
        mock_run_goal.assert_called_once_with(
            goal="add a validator", files=[], max_active=3, max_impl=2, verbose=False
        )

    @patch("vibe_coders.cli.run_goal")
    @patch("vibe_coders.cli.asyncio.run")
    def test_main_passes_files(self, mock_asyncio_run, mock_run_goal):
        mock_run_goal.side_effect = lambda **kwargs: asyncio.sleep(0)
        mock_asyncio_run.side_effect = lambda coro: {
            "active_agents": 0, "impl_busy": 0,
            "max_active_agents": 5, "max_impl_concurrent": 1,
            "tasks": {}, "agents": {},
        }
        main(["--goal", "x", "--files", "a.py", "b.py", "--max-active", "5", "--max-impl", "1", "--verbose", "--json"])
        call_kwargs = mock_run_goal.call_args[1]
        self.assertEqual(call_kwargs["goal"], "x")
        self.assertEqual(call_kwargs["files"], ["a.py", "b.py"])
        self.assertEqual(call_kwargs["max_active"], 5)
        self.assertEqual(call_kwargs["max_impl"], 1)
        self.assertEqual(call_kwargs["verbose"], True)


class RunGoalTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_goal_structure(self):
        report = await run_goal(
            goal="write a config validator",
            files=["vibe_coders/supervisor.py"],
            verbose=False,
        )
        self.assertIn("active_agents", report)
        self.assertIn("tasks", report)
        self.assertIn("agents", report)

    async def test_run_goal_respects_limits(self):
        report = await run_goal(
            goal="test something",
            max_active=1,
            max_impl=1,
        )
        self.assertEqual(report["max_active_agents"], 1)
        self.assertEqual(report["max_impl_concurrent"], 1)


class CLIRAGAgentMappingTests(unittest.TestCase):
    def test_agent_for_rag_roles(self):
        self.assertIsInstance(_agent_for("rag-research", "rag-res-1"), RAGResearchAgent)
        self.assertIsInstance(_agent_for("rag-verifier", "rag-ver-1"), RAGVerifierAgent)

    def test_file_owns_for_rag_roles(self):
        self.assertEqual(_file_owns_for("rag-research", {}), [])
        self.assertEqual(_file_owns_for("rag-verifier", {}), [])


class CLIRAGIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_rag_integration_structure(self):
        report = await run_rag_integration(
            rag_repo="/workspace/rag-team",
            max_active=3,
            max_impl=2,
            verbose=False,
        )
        self.assertEqual(report["mode"], "rag_integration")
        self.assertEqual(report["rag_repo"], "/workspace/rag-team")
        self.assertIn("research", report)
        self.assertIn("verification", report)
        self.assertIn("supervisor_report", report)
        self.assertIn("all_passed", report)

