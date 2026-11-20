"""Agent subpackage.

Specialist agent implementations: research, implementation, test, review, fix.
All are passive — they receive a context dict and return a result dict. The
Supervisor owns delegation, concurrency, and file ownership.
"""

from .base import BaseAgent, AgentProfile, register_profile, AGENT_PROFILES, ROLES, IMPLEMENTATION_ROLES
from .research import ResearchAgent
from .implementation import ImplementationAgent
from .test_agent import TestAgent
from .review_agent import ReviewAgent
from .fix_agent import FixAgent

__all__ = [
    "BaseAgent",
    "AgentProfile",
    "register_profile",
    "AGENT_PROFILES",
    "ROLES",
    "IMPLEMENTATION_ROLES",
    "ResearchAgent",
    "ImplementationAgent",
    "TestAgent",
    "ReviewAgent",
    "FixAgent",
]
