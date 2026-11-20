"""Implementation agent — writes isolated modules and tests.

Owns the files it is delegated. The Supervisor enforces single-writer
semantics, so no two implementation agents touch the same file simultaneously.
"""

from __future__ import annotations

from pathlib import Path

from .base import BaseAgent, register_profile, AgentProfile


register_profile(
    AgentProfile(
        role="implementation",
        write_allowlist={"vibe_coders/", "tests/"},
        purpose="Implements isolated modules and tests; writes only its assigned files.",
    )
)


class ImplementationAgent(BaseAgent):
    role = "implementation"
    write_allowlist = {"vibe_coders/", "tests/"}
    purpose = "Implement isolated modules and tests"

    def __init__(self, agent_id: str):
        super().__init__(agent_id)

    def run(self, context: dict) -> dict:
        path = context.get("path")
        content = context.get("content", "")
        if not path:
            return {"status": "failed", "error": "no path provided"}

        p = Path(path)
        # safety: stay within the project root (vibe_coders/ or tests/)
        parts = set(p.parts)
        if not ({"vibe_coders", "tests"} & parts):
            return {"status": "failed", "error": f"path outside allowed scope: {path}"}

        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {
            "status": "completed",
            "detail": f"wrote {path}",
            "path": str(p),
            "bytes": len(content.encode("utf-8")),
        }
