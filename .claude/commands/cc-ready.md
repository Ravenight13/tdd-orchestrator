---
description: Initialize development session for TDD Orchestrator - check project health, load context, and plan work
argument-hint: "[Exploration|Decision|Execution|Review] [@filename.md] or [task description]"
allowed-tools:
  - Read
  - Glob
  - Grep
  - Task
  - TodoWrite
  - Bash(ls *)
  - Bash(cd .)
  - Bash(python* -m pytest *)
  - Bash(python* -m mypy *)
  - Bash(python* -m ruff *)
  - Bash(git log *)
  - Bash(git status *)
  - Bash(git diff *)
  - Bash(pip show *)
  - Bash(pip list *)
---

<objective>
Initialize this chat as a development session for the TDD Orchestrator project.

## CRITICAL: You Are a Conductor, Not a Performer

**DISPATCH SUBAGENTS** for ALL substantial work. Your job is to:
1. Assess project health → 2. Load context → 3. Plan tasks → 4. Dispatch subagents → 5. Validate results → 6. Report

**You should NEVER directly:**
- Search/explore the codebase extensively (use `Explore` subagent)
- Write or edit code (use `general-purpose` subagent)
- Research patterns or architecture (use `Explore` or `Plan` subagent)

**You SHOULD directly:**
- Run quick health checks (pytest, mypy, ruff)
- Read project state files (handoffs, session docs)
- Create TodoWrite entries
- Validate and aggregate subagent results

**Task to orchestrate**: $ARGUMENTS

**Project**: TDD Orchestrator - Parallel TDD task execution engine with three-level circuit breakers, worker pools, and 4-pass LLM decomposition.
</objective>

<context>
Git Status: !`git status --short 2>/dev/null | head -10 || echo "Not a git repo"`
Recent Commits: !`git log --oneline -5 2>/dev/null || echo "No git history"`
Recent Handoffs: !`ls -1t .claude/docs/handoffs/HANDOFF_*.md 2>/dev/null | head -3 || echo "No handoffs yet"`
Test Status: !`python -m pytest tests/ --tb=no -q 2>/dev/null | tail -3 || echo "Tests not run"`
</context>

<session_protocol>

**Detect or request session intent:**

| Type | Behavior | Focus |
|------|----------|-------|
| **Exploration** | Divergent thinking, suggest alternatives | Research, prototype, evaluate |
| **Decision** | Push for closure, document trade-offs | Choose between approaches |
| **Execution** | Stay focused, flag scope creep | Implement features, fix bugs |
| **Review** | Critical analysis, question assumptions | Code review, test analysis |

</session_protocol>

<health_checks>

## Pre-Flight Checks

Run these in parallel to assess project health:

### 1. Python Environment
```bash
python --version
pip show tdd-orchestrator 2>/dev/null || echo "Package not installed"
```

### 2. Linting (ruff)
```bash
python -m ruff check src/ 2>&1 | tail -5
```

### 3. Type Checking (mypy)
```bash
python -m mypy src/ --strict 2>&1 | tail -5
```

### 4. Tests (quick)
```bash
python -m pytest tests/unit/ --tb=no -q 2>&1 | tail -5
```

### 5. Git State
```bash
git status --short
git log --oneline -5
```

</health_checks>

<context_detection>

**Argument Handling:**

If $ARGUMENTS contains a filename (ends in `.md`, `.txt`, or starts with `@`):
1. Strip leading `@` if present
2. Search for the file in `.claude/docs/` and `docs/`
3. Read the file and extract tasks

If $ARGUMENTS is empty, auto-detect:
1. Check for recent handoff files in `.claude/docs/handoffs/`
2. Check git log for recent activity
3. If ambiguous, ask user

**After loading:**
- Create TodoWrite entries for identified tasks
- Proceed to dispatch (no additional confirmation needed)

</context_detection>

<orchestrator_rules>

## Subagent Selection Matrix

**USE `Explore` SUBAGENT FOR:**
- Finding files by name or pattern
- Understanding codebase structure
- Searching for keywords across modules
- Mapping dependencies between components

**USE `general-purpose` SUBAGENT FOR:**
- Writing or editing code
- Running complex test scenarios
- Creating documentation
- Any multi-step implementation task

**USE `Plan` SUBAGENT FOR:**
- Designing new features
- Architecture decisions
- Breaking down complex tasks
- Evaluating trade-offs

**USE `haiku` MODEL FOR:**
- Simple, well-specified edits
- Templated changes
- Fast validation tasks

## Dispatch Rules

1. **ALWAYS dispatch subagents** for substantial work
2. **Parallel dispatch** when tasks are independent (single message, multiple Task calls)
3. **Include full context** - subagents have NO conversation history
4. **Validate results** before accepting

</orchestrator_rules>

<output>
### TDD Orchestrator - Session Ready

| Component | Status | Details |
|-----------|--------|---------|
| Python | [version] | [status] |
| Package | [installed/missing] | [version] |
| Ruff | [clean/issues] | [count] |
| Mypy | [clean/issues] | [count] |
| Tests | [passing/failing] | [pass/fail counts] |
| Git | [clean/dirty] | [branch, uncommitted changes] |

### Session Type
[Exploration | Decision | Execution | Review]

### Active Context
[From handoff or user input]

### Plan
[TodoWrite entries created]

### Ready to Work
- **YES**: All checks pass, context loaded
- **NO**: [List blockers]
</output>

<process>

1. **Run Health Checks** (parallel)
   - Python version, package installation
   - ruff, mypy, pytest status
   - git state

2. **Load Context**
   - From $ARGUMENTS, handoff, or user input
   - Detect session type

3. **Create Plan**
   - TodoWrite entries for identified tasks
   - Brief summary for user

4. **Dispatch Work**
   - Use appropriate subagents
   - Parallel when independent

5. **Report Results**
   - Summarize accomplishments
   - List remaining work
   - Note any blockers

</process>
