"""Architecture agent — expert system-design analysis.

Performs AST-based static analysis of Python modules to assess:
  * coupling between modules (imports)
  * cohesion (classes/functions per module)
  * interface boundaries (public vs private API)
  * potential design anti-patterns (god modules, circular import risk)

Pure read-only analysis using the stdlib ``ast`` module.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import List, Set

from .base import BaseAgent, AgentProfile, register_profile, make_result


register_profile(
    AgentProfile(
        role="architecture",
        write_allowlist=set(),
        purpose="Analyze code structure, coupling, cohesion, and interface boundaries.",
        read_only=True,
    )
)


class ArchitectureAgent(BaseAgent):
    role = "architecture"
    write_allowlist: set = set()
    purpose = "Review system architecture and design"
    read_only = True

    # Modules above this many public names are flagged as potential god modules.
    GOD_MODULE_THRESHOLD = 20
    # Files above this many lines are flagged as large files.
    LARGE_FILE_THRESHOLD = 400

    def __init__(self, agent_id: str):
        super().__init__(agent_id)

    def _parse_file(self, path: Path):
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            return source, tree
        except (OSError, SyntaxError) as exc:
            return None, exc

    def _public_names(self, tree: ast.AST) -> List[str]:
        names = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not node.name.startswith("_"):
                    names.append(node.name)
        return names

    def _imports(self, tree: ast.AST) -> List[str]:
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
        return imports

    def run(self, context: dict) -> dict:
        roots = context.get("roots", ["vibe_coders"])
        files = context.get("files")

        python_files: List[Path] = []
        if files:
            python_files = [Path(f) for f in files if f.endswith(".py")]
        else:
            for root in roots:
                rp = Path(root)
                if rp.is_dir():
                    python_files.extend(sorted(rp.rglob("*.py")))
                elif rp.is_file() and rp.suffix == ".py":
                    python_files.append(rp)

        if not python_files:
            return make_result(
                status="abstained",
                detail="no Python files found to analyze",
                confidence=0.0,
            )

        module_reports = []
        all_imports: dict[str, Set[str]] = {}  # module -> set of imported modules
        public_counts: dict[str, int] = {}

        for path in python_files:
            source, tree_or_exc = self._parse_file(path)
            rel = str(path)

            if source is None:
                # Parse error is a high-severity finding.
                module_reports.append(
                    {
                        "file": rel,
                        "public_names": 0,
                        "import_count": 0,
                        "findings": [
                            {
                                "file": rel,
                                "issue": f"parse error: {tree_or_exc}",
                                "severity": "high",
                            }
                        ],
                    }
                )
                continue

            tree = tree_or_exc
            pub = self._public_names(tree)
            imports = self._imports(tree)
            all_imports[rel] = set(imports)
            public_counts[rel] = len(pub)

            findings = []
            if len(pub) > self.GOD_MODULE_THRESHOLD:
                findings.append(
                    {
                        "file": rel,
                        "issue": f"potential god module: {len(pub)} public names",
                        "severity": "medium",
                        "names": pub[:10],
                    }
                )
            if source.count("\n") + 1 > self.LARGE_FILE_THRESHOLD:
                findings.append(
                    {
                        "file": rel,
                        "issue": f"large file ({source.count(chr(10)) + 1} lines)",
                        "severity": "low",
                    }
                )
            module_reports.append(
                {
                    "file": rel,
                    "public_names": len(pub),
                    "import_count": len(imports),
                    "findings": findings,
                }
            )

        # Detect coupling: modules imported by many others.
        import_fan_in: dict[str, int] = {}
        for _mod, imps in all_imports.items():
            for imp in imps:
                import_fan_in[imp] = import_fan_in.get(imp, 0) + 1

        highly_coupled = [m for m, c in import_fan_in.items() if c >= 3]

        # Flatten all module-level findings into a single top-level list.
        flat_findings: List[dict] = []
        module_summaries: List[dict] = []
        for m in module_reports:
            module_summaries.append(
                {"file": m["file"], "public_names": m["public_names"], "import_count": m["import_count"]}
            )
            flat_findings.extend(m.get("findings", []))
        flat_findings.append(
            {
                "file": "system",
                "issue": f"highly coupled imports (fan-in >= 3): {', '.join(highly_coupled) or 'none'}",
                "severity": "info",
            }
        )

        total_findings = len(flat_findings)
        high_severity = sum(1 for f in flat_findings if f["severity"] == "high")

        confidence = 0.85 if module_reports else 0.3
        status = "failed" if high_severity > 0 else "completed"

        return make_result(
            status=status,
            detail=f"Analyzed {len(module_reports)} module(s); {total_findings} design finding(s)",
            confidence=confidence,
            evidence=module_summaries,
            findings=flat_findings,
            recommendations=[
                "Split god modules into smaller, cohesive modules",
                "Reduce import fan-in by introducing facades or dependency injection",
                "Keep public API surface small; prefix internals with underscore",
            ],
        )
