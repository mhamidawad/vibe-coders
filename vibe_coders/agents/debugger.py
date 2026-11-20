"""Debugger agent — expert root-cause analysis.

Analyzes failure evidence (error messages, stack traces, test output, agent
results) to produce a root-cause hypothesis, confidence, and a targeted fix
recommendation. Pure analysis: never writes project files.
"""

from __future__ import annotations

import re
from typing import List

from .base import BaseAgent, AgentProfile, register_profile, make_result


register_profile(
    AgentProfile(
        role="debugger",
        write_allowlist=set(),
        purpose="Diagnose failures from traces/logs/results and propose root-cause fixes.",
        read_only=True,
    )
)


class DebuggerAgent(BaseAgent):
    role = "debugger"
    write_allowlist: set = set()
    purpose = "Diagnose root causes of failures"
    read_only = True

    # Pattern -> (likely cause, fix suggestion, confidence boost)
    ERROR_PATTERNS = [
        (
            r"ModuleNotFoundError|ImportError",
            "Missing dependency or module not on sys.path",
            "Install the missing module or correct the import path.",
            0.9,
        ),
        (
            r"SyntaxError",
            "Invalid Python syntax",
            "Correct the syntax at the reported line and column.",
            0.95,
        ),
        (
            r"AttributeError",
            "Attribute access on None or wrong type",
            "Guard attribute access or fix the upstream type.",
            0.8,
        ),
        (
            r"TypeError",
            "Type mismatch in call or operation",
            "Align argument types with the function signature.",
            0.85,
        ),
        (
            r"FileNotFoundError",
            "Referenced path does not exist",
            "Create the file, correct the path, or guard with existence check.",
            0.9,
        ),
        (
            r"PermissionError",
            "Filesystem permission denied",
            "Adjust file permissions or run with appropriate privileges.",
            0.85,
        ),
        (
            r"TimeoutExpired|timed out",
            "Operation exceeded its time budget",
            "Increase the timeout, optimize the operation, or run in background.",
            0.75,
        ),
        (
            r"ConnectionRefusedError|connection refused",
            "Service not listening on the expected port",
            "Start the service, verify the port/host, or check firewall.",
            0.85,
        ),
        (
            r"assert|AssertionError",
            "An assertion failed",
            "Re-examine the invariant; the assumed condition is false.",
            0.8,
        ),
    ]

    def __init__(self, agent_id: str):
        super().__init__(agent_id)

    def _analyze_text(self, text: str) -> List[dict]:
        findings = []
        for pattern, cause, fix, conf in self.ERROR_PATTERNS:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                line_start = text.rfind("\n", 0, match.start()) + 1
                line_end = text.find("\n", match.end())
                if line_end == -1:
                    line_end = len(text)
                snippet = text[line_start:line_end].strip()
                findings.append(
                    {
                        "pattern": pattern,
                        "snippet": snippet[:200],
                        "likely_cause": cause,
                        "suggested_fix": fix,
                        "confidence": conf,
                        "position": match.start(),
                    }
                )
        return findings

    def run(self, context: dict) -> dict:
        error_text = context.get("error_text") or context.get("stderr") or ""
        agent_result = context.get("agent_result") or {}
        task_title = context.get("task_title", "unknown task")

        # Combine all available failure evidence.
        evidence_parts = [error_text]
        if agent_result.get("error"):
            evidence_parts.append(str(agent_result["error"]))
        if agent_result.get("detail"):
            evidence_parts.append(str(agent_result["detail"]))
        combined = "\n".join(part for part in evidence_parts if part)

        findings = self._analyze_text(combined)

        if not findings:
            return make_result(
                status="abstained",
                detail=f"No recognizable failure pattern in evidence for task {task_title}",
                confidence=0.4,
                evidence=[combined[:500]] if combined else [],
                recommendations=[
                    "Capture full stderr and stdout from the failing run",
                    "Re-run with verbose logging to expose the root cause",
                ],
            )

        # Pick the highest-confidence finding as the primary hypothesis.
        primary = max(findings, key=lambda f: f["confidence"])
        overall_confidence = min(0.95, primary["confidence"] + 0.05 * len(findings))

        return make_result(
            status="completed",
            detail=f"Identified {len(findings)} failure indicator(s); primary: {primary['likely_cause']}",
            confidence=overall_confidence,
            evidence=[combined[:1000]] if combined else [],
            findings=findings,
            recommendations=[
                primary["suggested_fix"],
                "Apply the fix, then re-run the failing task to confirm resolution",
                "If the same error recurs twice, escalate to architecture review",
            ],
        )
