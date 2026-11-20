"""Orchestrator — demonstrates multi-agent expert collaboration.

This is a reference workflow showing how the Supervisor coordinates specialist
agents to accomplish a goal end-to-end:

  1. Planner   — decompose the goal into subtasks
  2. Research  — investigate the codebase
  3. Architecture — review design/coupling
  4. Implementation — write code
  5. Test — run tests
  6. Review — code review
  7. Security — security scan
  8. Debugger — diagnose any failures
  9. Documentation — generate docs

Run with:  python -m vibe_coders.orchestrator
"""

from __future__ import annotations

from vibe_coders.supervisor import Supervisor
from vibe_coders.agents import (
    PlannerAgent,
    ResearchAgent,
    ArchitectureAgent,
    ImplementationAgent,
    TestAgent,
    ReviewAgent,
    SecurityAgent,
    DebuggerAgent,
    DocumentationAgent,
)


def _agent_for(role: str, agent_id: str):
    cls = {
        "planner": PlannerAgent,
        "research": ResearchAgent,
        "architecture": ArchitectureAgent,
        "implementation": ImplementationAgent,
        "test": TestAgent,
        "review": ReviewAgent,
        "security": SecurityAgent,
        "debugger": DebuggerAgent,
        "documentation": DocumentationAgent,
    }[role]
    return cls(agent_id)


def run_demo():
    sup = Supervisor()

    print("=== Veteran-Grade Specialist Agents: expert orchestration demo ===\n")

    # 1. Planner decomposes the goal
    goal = "Add a config validator module, test it, review it, scan for security issues, and document it"
    plan = sup.plan_goal(goal, files=["vibe_coders/supervisor.py"])
    print(f"[planner] {plan['detail']} (confidence={plan['confidence']:.2f})")
    for st in plan.get("findings", []):
        print(f"   - {st['id']}: {st['title']} -> {st['role']} (effort={st['effort']})")

    # 2. Research the codebase
    research = _agent_for("research", "res-1")
    t_research = sup.new_task("inventory codebase", "research", file_owns=[])
    sup.delegate(t_research.id, research)
    r = sup.run(t_research.id, research, {"root": "vibe_coders", "pattern": "*.py"})
    print(f"\n[research] {r['detail']} (confidence={r['confidence']:.2f})")
    print(f"   matches: {len(r.get('matches', []))} files")

    # 3. Architecture review
    arch = _agent_for("architecture", "arch-1")
    t_arch = sup.new_task("review architecture", "architecture", file_owns=[])
    sup.delegate(t_arch.id, arch)
    r = sup.run(t_arch.id, arch, {"roots": ["vibe_coders"]})
    print(f"\n[architecture] {r['detail']} (confidence={r['confidence']:.2f})")
    for f in r.get("findings", [])[:3]:
        print(f"   - {f.get('file')}: {f.get('issue')} ({f.get('severity')})")

    # 4. Implementation: write a config validator module
    impl = _agent_for("implementation", "impl-1")
    t_impl = sup.new_task(
        "write config validator", "implementation",
        file_owns=["vibe_coders/config_validator.py"],
    )
    sup.delegate(t_impl.id, impl)
    code = '''"""Configuration validation utilities.

Provides validation for application configuration dictionaries.
"""

from __future__ import annotations

from typing import Any, Dict, List


def validate_config(config: Dict[str, Any], required_keys: List[str]) -> List[str]:
    """Return a list of missing required keys from config."""
    missing = [k for k in required_keys if k not in config]
    return missing


def is_valid(config: Dict[str, Any], required_keys: List[str]) -> bool:
    """Return True if config contains all required keys."""
    return len(validate_config(config, required_keys)) == 0
'''
    r = sup.run(t_impl.id, impl, {"path": "vibe_coders/config_validator.py", "content": code})
    print(f"\n[implementation] {r['detail']} (confidence={r['confidence']:.2f})")

    # 5. Test: run the test suite
    tester = _agent_for("test", "test-1")
    t_test = sup.new_task("run tests", "test", file_owns=[])
    sup.delegate(t_test.id, tester)
    r = sup.run(t_test.id, tester, {"test_paths": ["tests"]})
    print(f"\n[test] {r['detail']} (confidence={r['confidence']:.2f})")
    print(f"   passed={r.get('passed')} returncode={r.get('returncode')}")

    # 6. Review: review the new module
    reviewer = _agent_for("review", "rev-1")
    t_review = sup.new_task("review config_validator", "review", file_owns=[])
    sup.delegate(t_review.id, reviewer)
    r = sup.run(t_review.id, reviewer, {"paths": ["vibe_coders/config_validator.py"]})
    print(f"\n[review] {r['detail']} (confidence={r['confidence']:.2f})")
    for f in r.get("findings", [])[:3]:
        print(f"   - {f.get('file')}:{f.get('line')} {f.get('issue')} ({f.get('severity')})")

    # 7. Security scan
    sec = _agent_for("security", "sec-1")
    t_sec = sup.new_task("security scan", "security", file_owns=[])
    sup.delegate(t_sec.id, sec)
    r = sup.run(t_sec.id, sec, {"roots": ["vibe_coders"]})
    print(f"\n[security] {r['detail']} (confidence={r['confidence']:.2f})")
    for f in r.get("findings", [])[:5]:
        print(f"   - {f.get('file')}: {f.get('issue')} ({f.get('severity')})")

    # 8. Documentation
    doc = _agent_for("documentation", "doc-1")
    t_doc = sup.new_task("document config_validator", "documentation", file_owns=[])
    sup.delegate(t_doc.id, doc)
    r = sup.run(t_doc.id, doc, {"roots": ["vibe_coders"]})
    print(f"\n[documentation] {r['detail']} (confidence={r['confidence']:.2f})")

    # Final report
    print("\n=== Supervisor report ===")
    report = sup.report()
    print(f"active_agents={report['active_agents']} / {report['max_active_agents']}")
    print(f"impl_busy={report['impl_busy']} / {report['max_impl_concurrent']}")
    for tid, t in report["tasks"].items():
        print(f"  {tid} [{t['role']}]: {t['status']} confidence={t['confidence']} strategy_change={t['strategy_change']}")


if __name__ == "__main__":
    run_demo()
