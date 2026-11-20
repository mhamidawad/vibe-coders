"""Agent subpackage.

Specialist agent implementations: research, implementation, test, review, fix,
planner, architecture, debugger, security, documentation.

All are passive — they receive a context dict and return a result dict with
status, confidence, evidence, findings, and recommendations. The Supervisor
owns delegation, concurrency, and file ownership.
"""

from .base import (
    AgentProfile,
    BaseAgent,
    IMPLEMENTATION_ROLES,
    ROLES,
    AGENT_PROFILES,
    register_profile,
    make_result,
)
from .architecture import ArchitectureAgent
from .debugger import DebuggerAgent
from .documentation import DocumentationAgent
from .fix_agent import FixAgent
from .implementation import ImplementationAgent
from .planner import PlannerAgent
from .review_agent import ReviewAgent
from .security import SecurityAgent
from .test_agent import TestAgent
from .research import ResearchAgent

__all__ = [
    "AgentProfile",
    "BaseAgent",
    "IMPLEMENTATION_ROLES",
    "ROLES",
    "AGENT_PROFILES",
    "register_profile",
    "make_result",
    "ResearchAgent",
    "ImplementationAgent",
    "TestAgent",
    "ReviewAgent",
    "FixAgent",
    "PlannerAgent",
    "ArchitectureAgent",
    "DebuggerAgent",
    "SecurityAgent",
    "DocumentationAgent",
]
