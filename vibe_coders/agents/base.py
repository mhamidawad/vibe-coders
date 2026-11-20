"""Agent base class and role definitions.

Every specialist agent subclasses BaseAgent and declares the role it fulfills
and the file paths it is allowed to write. The Supervisor uses this metadata
to enforce file-ownership and concurrency constraints.

All agents return a structured result dict with at least:

    status      - "completed" | "failed" | "abstained"
    detail      - human-readable summary
    confidence  - float 0..1 (expert certainty in the result)
    evidence    - list of supporting references (file paths, line numbers, ...)
    findings    - list of finding dicts (role-specific)
    recommendations - list of suggested next actions
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Set


# The canonical set of agent roles. Keep in sync with registry.py.
ROLES = (
    "supervisor",
    "research",
    "implementation",
    "test",
    "review",
    "fix",
    "planner",
    "architecture",
    "debugger",
    "security",
    "documentation",
)

# Roles whose agents produce code / file edits. Concurrency for these is
# capped at 2 by the Supervisor (per mission rules).
IMPLEMENTATION_ROLES = frozenset(
    {"implementation", "fix", "review", "planner", "architecture", "debugger", "security", "documentation"}
)


@dataclass
class AgentProfile:
    """Static metadata describing one agent kind."""

    role: str
    # File path prefixes this agent is permitted to write. Empty set = any.
    write_allowlist: Set[str] = field(default_factory=set)
    # Human-readable purpose.
    purpose: str = ""
    # Whether this agent only performs read-only reconnaissance.
    read_only: bool = False


# Registry of agent profiles. Specialists register here so the Supervisor can
# validate assignments without importing every agent module.
AGENT_PROFILES: dict[str, AgentProfile] = {}


def register_profile(profile: AgentProfile) -> None:
    AGENT_PROFILES[profile.role] = profile


def make_result(
    *,
    status: str = "completed",
    detail: str = "",
    confidence: float = 1.0,
    evidence=None,
    findings=None,
    recommendations=None,
    **extra,
) -> dict:
    """Build a standardized agent result dict."""
    return {
        "status": status,
        "detail": detail,
        "confidence": max(0.0, min(1.0, float(confidence))),
        "evidence": list(evidence or []),
        "findings": list(findings or []),
        "recommendations": list(recommendations or []),
        **extra,
    }


class BaseAgent:
    """Base class for all specialist agents.

    Subclasses set ``role`` and ``write_allowlist``, and implement ``run``.
    Agents are intentionally stateless and side-effect free by default; the
    Supervisor owns all mutation of shared state (registry, task store).
    """

    role: str = "base"
    write_allowlist: Set[str] = set()
    purpose: str = ""
    read_only: bool = False

    def __init__(self, agent_id: str):
        self.agent_id = agent_id

    def can_write(self, path: str) -> bool:
        """Return True if this agent may write the given path."""
        if self.read_only:
            return False
        if not self.write_allowlist:
            return True
        return any(path.startswith(prefix) for prefix in self.write_allowlist)

    def run(self, context: dict) -> dict:
        """Execute the agent's work for one task.

        Returns a result dict produced by :func:`make_result`.
        """
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"{self.__class__.__name__}(role={self.role!r}, id={self.agent_id!r})"
