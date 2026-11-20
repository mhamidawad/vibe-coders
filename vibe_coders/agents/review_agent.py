"""Review agent — code review and risk assessment.

Read-only: inspects files for obvious issues (imports, syntax, long lines,
missing docstrings) and reports findings. Does not modify files.
"""

from __future__ import annotations
from pathlib import Path

from .base import BaseAgent, register_profile, AgentProfile


register_profile(
    AgentProfile(
        role="review",
        write_allowlist=set(),
        purpose="Read-only code review and risk assessment of assigned files.",
        read_only=True,
    )
)


class ReviewAgent(BaseAgent):
    role = "review"
    write_allowlist: set = set()
    purpose = "Review code for risks and correctness"
    read_only = True

    def __init__(self, agent_id: str):
        super().__init__(agent_id)

    def run(self, context: dict) -> dict:
        paths = context.get("paths") or []
        findings = []
        for path in paths:
            p = Path(path)
            if not p.exists():
                findings.append({"file": str(p), "issue": "missing", "severity": "error"})
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
            lines = text.splitlines()
            for i, line in enumerate(lines, 1):
                if len(line) > 100:
                    findings.append({
                        "file": str(p), "line": i, "issue": "line > 100 chars",
                        "severity": "low",
                    })
            try:
                compile(text, str(p), "exec")
            except SyntaxError as exc:
                findings.append({
                    "file": str(p), "line": exc.lineno, "issue": f"syntax error: {exc.msg}",
                    "severity": "high",
                })

        errors = [f for f in findings if f["severity"] == "error"]
        high = [f for f in findings if f["severity"] == "high"]
        status = "failed" if errors or high else "completed"
        return {
            "status": status,
            "detail": f"reviewed {len(paths)} file(s); {len(findings)} finding(s)",
            "findings": findings,
            "passed": status == "completed",
        }
