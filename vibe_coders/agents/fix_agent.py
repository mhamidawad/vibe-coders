"""Fix agent — independent file fixes.

Applies targeted text replacements to files it owns. The Supervisor enforces
single-writer ownership, so fix agents never collide on the same file.
"""

from __future__ import annotations

from pathlib import Path

from .base import BaseAgent, register_profile, AgentProfile


register_profile(
    AgentProfile(
        role="fix",
        write_allowlist={"vibe_coders/", "tests/"},
        purpose="Apply independent, targeted fixes to assigned files only.",
    )
)


class FixAgent(BaseAgent):
    role = "fix"
    write_allowlist = {"vibe_coders/", "tests/"}
    purpose = "Apply independent file fixes"

    def __init__(self, agent_id: str):
        super().__init__(agent_id)

    def _in_scope(self, path: str) -> bool:
        parts = set(Path(path).parts)
        return bool({"vibe_coders", "tests"} & parts)

    def run(self, context: dict) -> dict:
        path = context.get("path")
        old = context.get("old")
        new = context.get("new")
        if not path or old is None or new is None:
            return {"status": "failed", "error": "need path, old, and new"}

        if not self._in_scope(path):
            return {"status": "failed", "error": f"path outside allowed scope: {path}"}

        p = Path(path)
        if not p.exists():
            return {"status": "failed", "error": f"file not found: {path}"}

        text = p.read_text(encoding="utf-8")
        if old not in text:
            return {"status": "failed", "error": f"old text not found in {path}"}

        p.write_text(text.replace(old, new, 1), encoding="utf-8")
        return {"status": "completed", "detail": f"fixed {path}", "path": str(p)}
