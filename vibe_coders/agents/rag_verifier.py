"""RAG verifier agent — runs MOe RAG verification commands and reports results.

Executes the RAG unit test suite and hallucination regression suite in the
RAG repo directory. Read-only: never modifies RAG files. Reports results
accurately, including pre-existing failures (never claims a pass).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .base import BaseAgent, AgentProfile, register_profile, make_result


register_profile(
    AgentProfile(
        role="rag-verifier",
        write_allowlist=set(),
        purpose="Verify MOe RAG remediation by running unit tests and hallucination suite.",
        read_only=True,
    )
)


class RAGVerifierAgent(BaseAgent):
    role = "rag-verifier"
    write_allowlist: set = set()
    purpose = "Verify RAG remediation (read-only execution)"
    read_only = True

    def __init__(self, agent_id: str):
        super().__init__(agent_id)

    def _run_command(self, cmd: list, cwd: Path, timeout: int = 120) -> dict:
        """Run a command and return a structured result."""
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(cwd),
            )
            return {
                "command": " ".join(cmd),
                "returncode": proc.returncode,
                "stdout": proc.stdout[-5000:],
                "stderr": proc.stderr[-3000:],
                "passed": proc.returncode == 0,
            }
        except subprocess.TimeoutExpired:
            return {
                "command": " ".join(cmd),
                "returncode": -1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout}s",
                "passed": False,
            }
        except FileNotFoundError as exc:
            return {
                "command": " ".join(cmd),
                "returncode": -1,
                "stdout": "",
                "stderr": f"Command not found: {exc}",
                "passed": False,
            }

    def run(self, context: dict) -> dict:
        rag_repo = context.get("rag_repo")
        if not rag_repo:
            return make_result(
                status="failed",
                detail="rag-verifier requires a 'rag_repo' path in context",
                confidence=0.0,
            )

        root = Path(rag_repo)
        if not root.is_dir():
            return make_result(
                status="failed",
                detail=f"RAG repo path is not a directory: {rag_repo}",
                confidence=0.0,
            )

        results = []

        # 1. Run unit tests.
        test_result = self._run_command(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests"], root
        )
        results.append({"suite": "unit_tests", **test_result})

        # 2. Run hallucination regression suite (no inference).
        halluc_result = self._run_command(
            [sys.executable, "tasks/verify-hallucination.py"], root
        )
        results.append({"suite": "hallucination_suite", **halluc_result})

        # Summarize.
        total_suites = len(results)
        passed_suites = sum(1 for r in results if r["passed"])
        all_passed = passed_suites == total_suites

        # Collect any pre-existing failures for honest reporting.
        failures = []
        for r in results:
            if not r["passed"]:
                failures.append(
                    {
                        "suite": r["suite"],
                        "returncode": r["returncode"],
                        "stderr_tail": r["stderr"][-300:] if r["stderr"] else "",
                    }
                )

        status = "completed" if all_passed else "completed"  # verifier completes; reports accurately
        confidence = 0.85 if root.is_dir() else 0.0

        return make_result(
            status=status,
            detail=f"RAG verification: {passed_suites}/{total_suites} suite(s) passed",
            confidence=confidence,
            evidence=[str(root)],
            findings=[
                {
                    "suite": r["suite"],
                    "passed": r["passed"],
                    "returncode": r["returncode"],
                }
                for r in results
            ],
            recommendations=[
                "Fix pre-existing test failures before claiming full remediation pass",
                "Run hallucination suite in CI (zero inference calls)",
                "Complete supervisor_integration (item 4) for end-to-end acceptance",
            ]
            + (
                [
                    f"Pre-existing failure in {f['suite']}: {f['stderr_tail']}"
                    for f in failures[:3]
                ]
                if failures
                else []
            ),
            test_results=results,
            all_passed=all_passed,
        )
