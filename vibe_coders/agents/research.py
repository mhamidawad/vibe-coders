"""Research agent — read-only codebase investigation and discovery.

Performs reconnaissance only: listing files, searching contents, and
summarizing structure. It never writes files (read_only=True).
"""

from __future__ import annotations

import os
from typing import List

from .base import BaseAgent, register_profile, AgentProfile


register_profile(
    AgentProfile(
        role="research",
        write_allowlist=set(),
        purpose="Read-only codebase investigation: file discovery, content search, structure summary.",
        read_only=True,
    )
)


class ResearchAgent(BaseAgent):
    role = "research"
    write_allowlist: set = set()
    purpose = "Read-only codebase investigation"
    read_only = True

    def __init__(self, agent_id: str):
        super().__init__(agent_id)

    def run(self, context: dict) -> dict:
        root = context.get("root", ".")
        pattern = context.get("pattern", "*")
        search_term = context.get("search_term")

        matches: List[str] = []
        for dirpath, _dirnames, filenames in os.walk(root):
            # skip common noise directories
            if any(part in {".git", "__pycache__", ".venv", "node_modules"} for part in dirpath.split(os.sep)):
                continue
            for name in filenames:
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, root)
                if search_term:
                    try:
                        with open(full, "r", encoding="utf-8", errors="ignore") as fh:
                            if search_term in fh.read():
                                matches.append(rel)
                    except OSError:
                        continue
                else:
                    matches.append(rel)

        matches.sort()
        return {
            "status": "completed",
            "detail": f"Found {len(matches)} file(s) matching pattern={pattern!r}" + (
                f" containing {search_term!r}" if search_term else ""
            ),
            "matches": matches[:200],
            "root": root,
        }
