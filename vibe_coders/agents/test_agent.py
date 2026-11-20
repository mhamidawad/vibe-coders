"""Test agent — runs tests and verifies results.

Read-only with respect to source; it executes the project's test runner and
reports a pass/fail summary. It does not modify source files.
"""

from __future__ import annotations

import subprocess
import sys

from .base import BaseAgent, register_profile, AgentProfile


register_profile(
    AgentProfile(
        role="test",
        write_allowlist=set(),
        purpose="Run the test suite and verify results; read-only verification.",
        read_only=True,
    )
)


class TestAgent(BaseAgent):
    role = "test"
    write_allowlist: set = set()
    purpose = "Run tests and verify results"
    read_only = True

    def __init__(self, agent_id: str):
        super().__init__(agent_id)

    def run(self, context: dict) -> dict:
        test_paths = context.get("test_paths") or ["tests"]
        cmd = [sys.executable, "-m", "pytest", "-q"] + list(test_paths)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except FileNotFoundError:
            return {"status": "failed", "error": "pytest not available"}
        except subprocess.TimeoutExpired:
            return {"status": "failed", "error": "test run timed out"}

        passed = proc.returncode == 0
        return {
            "status": "completed" if passed else "failed",
            "detail": f"pytest exit code {proc.returncode}",
            "returncode": proc.returncode,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-2000:],
            "passed": passed,
        }
