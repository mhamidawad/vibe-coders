# vibe-coders

Veteran-Grade Specialist Agents — a supervised multi-agent orchestration
skeleton. A **Supervisor** coordinates specialist agents (research,
implementation, test, review, fix) through a shared task registry, with clear
file ownership, concurrency limits, and stage-gated execution.

## Design

```
Supervisor (single orchestration authority)
  ├── Registry  — agents, tasks, file ownership (single-writer)
  └── delegates to → specialist agents (passive, context-in / result-out)
```

### Agents

| Role | Responsibility | Writes |
|------|----------------|--------|
| `research` | Read-only codebase investigation & discovery | (none) |
| `implementation` | Writes isolated modules & tests | `vibe_coders/`, `tests/` |
| `test` | Runs tests & verifies results | (none) |
| `review` | Code review & risk assessment | (none) |
| `fix` | Targeted independent file fixes | `vibe_coders/`, `tests/` |

### Constraints enforced by the Supervisor

- **Max 3 active agents** at once.
- **Max 2 concurrent implementation-role agents** (`implementation`, `fix`, `review`).
- **Single-writer file ownership**: no two agents may write the same file simultaneously.
- **Stage-gated execution**: discovery → implementation → testing → review → fixes → final_tests → deploy → verify.

## Stack

Python 3.12, stdlib-only. No model calls, no network, no Docker, no credentials,
no dependencies beyond `pytest` for testing.

## Commands

```bash
# create + activate venv (optional but recommended)
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# run tests
python3 -m pytest -q
# or
python3 -m unittest discover -s tests -v

# compile check
python3 -m compileall -q vibe_coders tests
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

## Status

Greenfield skeleton. No production containers, no credentials, no model changes.
Safe to run in any workspace.
