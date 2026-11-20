"""Security agent — expert security review.

Scans Python source and configuration for:
  * hardcoded secrets (API keys, tokens, passwords)
  * dangerous builtins (eval, exec, compile with user input)
  * shell injection vectors (shell=True with string concatenation)
  * unsafe deserialization (pickle.loads, yaml.load without SafeLoader)
  * overly permissive file/network bindings (0.0.0.0, --network host)

Pure read-only static analysis using regex and stdlib ``ast``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import List

from .base import BaseAgent, AgentProfile, register_profile, make_result


register_profile(
    AgentProfile(
        role="security",
        write_allowlist=set(),
        purpose="Scan for secrets, dangerous builtins, injection vectors, and permissive bindings.",
        read_only=True,
    )
)


class SecurityAgent(BaseAgent):
    role = "security"
    write_allowlist: set = set()
    purpose = "Perform static security review"
    read_only = True

    SECRET_PATTERNS = [
        (r"(?i)(api[_-]?key|apikey)\s*[:=]\s*['\"][^'\"]{8,}", "hardcoded API key"),
        (r"(?i)(secret|token)\s*[:=]\s*['\"][^'\"]{8,}", "hardcoded secret/token"),
        (r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"][^'\"]{4,}", "hardcoded password"),
        (r"(?i)(aws[_-]?secret|aws[_-]?access)\s*[:=]\s*['\"][^'\"]{8,}", "hardcoded AWS credential"),
    ]

    DANGEROUS_CALLS = [
        (r"\beval\s*\(", "eval() with potential user input"),
        (r"\bexec\s*\(", "exec() with potential user input"),
        (r"\bcompile\s*\(", "compile() with potential user input"),
        (r"\bpickle\.loads\s*\(", "unsafe pickle deserialization"),
        (r"\byaml\.load\s*\((?!.*Loader)", "yaml.load without SafeLoader"),
    ]

    SHELL_PATTERNS = [
        (r"shell\s*=\s*True", "shell=True enables shell injection"),
        (r"subprocess\.(run|call|Popen).*shell\s*=\s*True", "subprocess with shell=True"),
    ]

    BINDING_PATTERNS = [
        (r"0\.0\.0\.0", "bind to all interfaces (0.0.0.0)"),
        (r"--network\s+host", "Docker --network host"),
        (r"bind\s*\(\s*['\"]0\.0\.0\.0", "socket bind to all interfaces"),
    ]

    def __init__(self, agent_id: str):
        super().__init__(agent_id)

    def _scan_text(self, path: str, text: str) -> List[dict]:
        findings: List[dict] = []
        for pattern, description in self.SECRET_PATTERNS:
            for m in re.finditer(pattern, text):
                findings.append(
                    {
                        "file": path,
                        "issue": f"possible {description}",
                        "severity": "high",
                        "snippet": m.group(0)[:120],
                    }
                )
        for pattern, description in self.DANGEROUS_CALLS:
            for m in re.finditer(pattern, text):
                findings.append(
                    {
                        "file": path,
                        "issue": f"dangerous call: {description}",
                        "severity": "medium",
                        "snippet": m.group(0)[:120],
                    }
                )
        for pattern, description in self.SHELL_PATTERNS:
            for m in re.finditer(pattern, text):
                findings.append(
                    {
                        "file": path,
                        "issue": f"shell injection vector: {description}",
                        "severity": "medium",
                        "snippet": m.group(0)[:120],
                    }
                )
        for pattern, description in self.BINDING_PATTERNS:
            for m in re.finditer(pattern, text):
                findings.append(
                    {
                        "file": path,
                        "issue": f"permissive binding: {description}",
                        "severity": "medium",
                        "snippet": m.group(0)[:120],
                    }
                )
        return findings

    def run(self, context: dict) -> dict:
        roots = context.get("roots", ["vibe_coders"])
        files = context.get("files")

        targets: List[Path] = []
        if files:
            targets = [Path(f) for f in files if f.endswith((".py", ".json", ".yaml", ".yml", ".toml", ".cfg", ".txt"))]
        else:
            for root in roots:
                rp = Path(root)
                if rp.is_dir():
                    targets.extend(sorted(rp.rglob("*.py")))
                    targets.extend(sorted(rp.rglob("*.json")))
                    targets.extend(sorted(rp.rglob("*.yaml")))
                    targets.extend(sorted(rp.rglob("*.yml")))
                    targets.extend(sorted(rp.rglob("*.toml")))
                    targets.extend(sorted(rp.rglob("*.cfg")))
                elif rp.is_file():
                    targets.append(rp)

        if not targets:
            return make_result(
                status="abstained",
                detail="no scannable files found",
                confidence=0.0,
            )

        all_findings: List[dict] = []
        for path in targets:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            rel = str(path)
            all_findings.extend(self._scan_text(rel, text))

        high = sum(1 for f in all_findings if f["severity"] == "high")
        medium = sum(1 for f in all_findings if f["severity"] == "medium")

        status = "failed" if high > 0 else "completed"
        confidence = 0.9 if targets else 0.3

        return make_result(
            status=status,
            detail=f"Scanned {len(targets)} file(s); {high} high, {medium} medium finding(s)",
            confidence=confidence,
            evidence=[str(p) for p in targets],
            findings=all_findings,
            recommendations=[
                "Remove hardcoded secrets; use environment variables or a secrets manager",
                "Replace eval/exec with ast.literal_eval or explicit dispatch",
                "Avoid shell=True; pass args as a list to subprocess",
                "Bind services to 127.0.0.1 unless public access is required",
            ],
        )
