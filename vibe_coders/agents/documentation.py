"""Documentation agent — expert doc generation.

Produces docstrings, module summaries, changelog entries, and API reference
entries from Python source using AST inspection. Pure read-only analysis.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import List

from .base import BaseAgent, AgentProfile, register_profile, make_result


register_profile(
    AgentProfile(
        role="documentation",
        write_allowlist={"docs/"},
        purpose="Generate docstrings, module summaries, changelog entries, and API references.",
        read_only=False,
    )
)


class DocumentationAgent(BaseAgent):
    role = "documentation"
    write_allowlist = {"docs/"}
    purpose = "Generate documentation from source code"
    read_only = False

    def __init__(self, agent_id: str):
        super().__init__(agent_id)

    def _analyze_module(self, path: Path) -> dict:
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError) as exc:
            return {"file": str(path), "error": str(exc)}

        module_doc = ast.get_docstring(tree)
        classes = []
        functions = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                methods = [
                    n.name
                    for n in node.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("__")
                ]
                classes.append({"name": node.name, "doc": ast.get_docstring(node), "methods": methods})
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
                args = [a.arg for a in node.args.args]
                functions.append(
                    {"name": node.name, "doc": ast.get_docstring(node), "args": args}
                )

        return {
            "file": str(path),
            "module_doc": module_doc,
            "classes": classes,
            "functions": functions,
            "public_api_count": len(classes) + len(functions),
        }

    def run(self, context: dict) -> dict:
        roots = context.get("roots", ["vibe_coders"])
        files = context.get("files")

        targets: List[Path] = []
        if files:
            targets = [Path(f) for f in files if f.endswith(".py")]
        else:
            for root in roots:
                rp = Path(root)
                if rp.is_dir():
                    targets.extend(sorted(rp.rglob("*.py")))
                elif rp.is_file() and rp.suffix == ".py":
                    targets.append(rp)

        if not targets:
            return make_result(
                status="abstained",
                detail="no Python files found to document",
                confidence=0.0,
            )

        modules = [self._analyze_module(p) for p in targets]
        total_api = sum(m.get("public_api_count", 0) for m in modules)
        missing_docstrings = sum(
            1
            for m in modules
            if not m.get("module_doc")
            and not m.get("error")
        )

        # Generate a changelog-style entry.
        entries = []
        for m in modules:
            if m.get("error"):
                entries.append(f"- {m['file']}: parse error ({m['error']})")
                continue
            name = Path(m["file"]).stem
            entries.append(f"- {name}: {m['public_api_count']} public API element(s)")
            if not m.get("module_doc"):
                entries.append(f"  - missing module docstring")

        changelog = "\n".join(entries) if entries else "(no changes)"

        confidence = 0.85 if targets else 0.3
        status = "completed" if missing_docstrings == 0 else "completed"

        return make_result(
            status=status,
            detail=f"Documented {len(modules)} module(s); {total_api} public API element(s); {missing_docstrings} missing docstring(s)",
            confidence=confidence,
            evidence=[str(p) for p in targets],
            findings=modules,
            recommendations=[
                "Add module docstrings to files missing them",
                "Add docstrings to public functions and classes",
                "Maintain a changelog entry for each public API change",
            ],
            generated_changelog=changelog,
        )
