"""Planner agent — expert task decomposition and execution planning.

Takes a high-level goal and produces an ordered, dependency-aware plan of
subtasks, each annotated with the agent role best suited to execute it,
estimated effort, and required file inputs/outputs. Pure analysis: never
writes project files.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List

from .base import BaseAgent, AgentProfile, register_profile, make_result


register_profile(
    AgentProfile(
        role="planner",
        write_allowlist=set(),
        purpose="Decompose goals into ordered, dependency-aware subtasks with role assignment.",
        read_only=True,
    )
)


class PlannerAgent(BaseAgent):
    role = "planner"
    write_allowlist: set = set()
    purpose = "Plan and decompose tasks"
    read_only = True

    # Keywords that hint at which agent role should handle a subtask.
    # Ordered so more specific/action-oriented roles come later for tie-breaking.
    ROLE_HINTS = {
        "planner": {"plan", "decompose", "break down", "schedule", "orchestrate"},
        "research": {"investigate", "find", "search", "explore", "inventory", "discover"},
        "implementation": {"implement", "write", "create", "build", "code", "develop"},
        "test": {"test", "verify", "validate", "assert", "run tests", "coverage"},
        "review": {"review", "audit", "inspect", "check", "assess", "evaluate"},
        "fix": {"fix", "repair", "patch", "correct", "resolve", "remediate"},
        "architecture": {"design", "architecture", "structure", "interface", "coupling"},
        "debugger": {"debug", "diagnose", "root cause", "trace", "crash", "error"},
        "security": {"security", "vulnerability", "secret", "permission", "audit", "safe"},
        "documentation": {"document", "docstring", "readme", "changelog", "api doc"},
    }

    # Tie-break priority: when two roles score equally, the one listed first wins.
    TIE_BREAK = (
        "documentation",
        "review",
        "security",
        "debugger",
        "architecture",
        "planner",
        "research",
        "test",
        "fix",
        "implementation",
    )

    def __init__(self, agent_id: str):
        super().__init__(agent_id)

    def _infer_role(self, title: str) -> str:
        text = title.lower()
        scores = {}
        for role, keywords in self.ROLE_HINTS.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scores[role] = score
        if not scores:
            return "implementation"
        max_score = max(scores.values())
        tied = [role for role, score in scores.items() if score == max_score]
        for role in self.TIE_BREAK:
            if role in tied:
                return role
        return tied[0]

    def _estimate_effort(self, title: str, complexity_hints: List[str]) -> str:
        score = len(complexity_hints)
        if any(w in title.lower() for w in ("system", "architecture", "refactor", "migrate")):
            score += 2
        if score >= 4:
            return "high"
        if score >= 2:
            return "medium"
        return "low"

    def run(self, context: dict) -> dict:
        goal = context.get("goal", "")
        files = context.get("files", [])
        if not goal:
            return make_result(
                status="failed",
                detail="planner requires a 'goal' in context",
                confidence=0.0,
            )

        # Decompose the goal into subtasks by looking for conjunctions and
        # distinct verbs. This is a deterministic, explainable decomposition.
        raw_parts = re.split(r"\b(?:and|then|also|;|,)\b", goal, flags=re.IGNORECASE)
        subtasks = []
        for idx, part in enumerate([p.strip() for p in raw_parts if p.strip()], 1):
            if not part:
                continue
            role = self._infer_role(part)
            hints = [w for w in ("complex", "refactor", "integrate", "design", "secure") if w in part.lower()]
            subtasks.append(
                {
                    "id": f"subtask-{idx:03d}",
                    "title": part,
                    "role": role,
                    "effort": self._estimate_effort(part, hints),
                    "depends_on": [f"subtask-{idx-1:03d}"] if idx > 1 else [],
                    "input_files": files,
                    "output_files": [],
                }
            )

        # Identify which files are likely touched by each subtask (heuristic).
        for st in subtasks:
            touched = []
            for f in files:
                fname = Path(f).name.lower()
                if st["role"] == "test" and ("test" in fname or fname.startswith("test_")):
                    touched.append(f)
                elif st["role"] in ("implementation", "fix") and fname.endswith(".py"):
                    touched.append(f)
                elif st["role"] == "documentation" and fname in ("README.md",) or fname.endswith(".md"):
                    touched.append(f)
            st["output_files"] = touched

        confidence = 0.9 if subtasks else 0.4
        return make_result(
            status="completed",
            detail=f"Decomposed goal into {len(subtasks)} subtask(s)",
            confidence=confidence,
            evidence=[f"goal: {goal}"] + files,
            findings=subtasks,
            recommendations=[
                "Execute subtasks in dependency order via the Supervisor",
                "Re-plan if any subtask fails twice (strategy change)",
            ],
        )
