# vibe-coders

Veteran-Grade Specialist Agents — a supervised multi-agent orchestration
framework. A **Supervisor** coordinates specialist agents (research,
implementation, test, review, fix, planner, architecture, debugger, security,
documentation) through a shared task registry, with clear file ownership,
concurrency limits, stage-gated execution, confidence scoring, and
retry-with-strategy-change.

## Design

```
Supervisor (single orchestration authority)
  ├── Registry  — agents, tasks, file ownership (single-writer), concurrency gates
  ├── Planner   — goal decomposition into ordered subtasks
  └── delegates to → specialist agents (passive, context-in / result-out)
```

### Agents (10 roles)

| Role | Responsibility | Writes | Read-only |
|------|----------------|--------|-----------|
| `research` | Read-only codebase investigation & discovery | (none) | yes |
| `implementation` | Writes isolated modules & tests | `vibe_coders/`, `tests/` | no |
| `test` | Runs tests & verifies results | (none) | yes |
| `review` | Code review & risk assessment | (none) | yes |
| `fix` | Targeted independent file fixes | `vibe_coders/`, `tests/` | no |
| `planner` | Decomposes goals into ordered, dependency-aware subtasks | (none) | yes |
| `architecture` | AST-based design analysis: coupling, cohesion, god modules | (none) | yes |
| `debugger` | Root-cause diagnosis from error traces/logs/results | (none) | yes |
| `security` | Static scan: secrets, dangerous builtins, injection, permissive bindings | (none) | yes |
| `documentation` | Docstrings, module summaries, changelog, API reference | `docs/` | no |

### Constraints enforced by the Supervisor

- **Max 3 active agents** at once.
- **Max 2 concurrent implementation-role agents**.
- **Single-writer file ownership**: no two agents may write the same file simultaneously.
- **Stage-gated execution**: discovery → implementation → testing → review → fixes → final_tests → deploy → verify.
- **Retry-with-strategy-change**: after two identical failures on a task, the Supervisor stops retrying and sets `strategy_change=True`.
- **Confidence scoring**: every result carries a `confidence` (0..1), `evidence`, `findings`, and `recommendations`.

## Stack

Python 3.12, stdlib-only. Real static analysis via the `ast` module. No model calls,
no network, no Docker, no credentials, no dependencies beyond `pytest` for testing.

## Commands

```bash
# create + activate venv (optional but recommended)
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# run all tests
python3 -m pytest -q
# or
python3 -m unittest discover -s tests -v

# compile check
python3 -m compileall -q vibe_coders tests

# run the multi-agent orchestration demo
python3 -m vibe_coders.orchestrator
```

## Example usage

```python
from vibe_coders.supervisor import Supervisor
from vibe_coders.agents.implementation import ImplementationAgent

sup = Supervisor()
agent = ImplementationAgent("impl-1")
task = sup.new_task("write hello module", "implementation",
                    file_owns=["vibe_coders/hello.py"])
sup.delegate(task.id, agent)
sup.run(task.id, agent, {"path": "vibe_coders/hello.py", "content": "print('hi')\n"})
print(sup.report())
```

## Intelligent orchestration example

```python
from vibe_coders.supervisor import Supervisor
from vibe_coders.agents.debugger import DebuggerAgent

sup = Supervisor()
# 1. Decompose a goal
plan = sup.plan_goal("add a config validator, test it, and document it")
# 2. Create tasks from the plan
tasks = sup.create_tasks_from_plan(plan)
# 3. Execute each task with the appropriate agent
for t in tasks:
    agent = _agent_for(t.agent_role, f"{t.agent_role}-1")
    sup.delegate(t.id, agent)
    result = sup.run(t.id, agent, {"path": t.file_owns[0] if t.file_owns else None, "content": "..."})
    if result.get("strategy_change"):
        # two identical failures — escalate to debugger/architecture
        experts = sup.escalate_on_failure(t.id)
print(sup.report())
```

## Test results

```
63 tests, 0 failures — 26 core + 37 new (planner, architecture, debugger,
security, documentation, supervisor intelligence)
```

## Status

Greenfield framework. Safe to run in any workspace — no production containers,
no credentials, no model changes.
