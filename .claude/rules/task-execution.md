# Task Execution Discipline - TDD Orchestrator

Before writing any code or making any changes, Claude MUST plan the work first. This rule governs the gap between receiving a task and starting implementation.

---

## Applicability

### This Rule Applies When

The task involves **3 or more steps**, touches **2 or more files**, or has **any ambiguity** in approach. Examples:
- Adding or modifying async database operations
- Creating or refactoring modules (especially near the 400-line split threshold)
- Multi-file edits (model + database + tests)
- Circuit breaker or worker pool changes
- Decomposition pipeline modifications
- Any task tied to a plan file in `.claude/docs/scratchpads/`

### This Rule Does NOT Apply When

The task is trivial and self-contained. Examples:
- Single-line fix (typo, rename)
- Reading/querying information only
- Answering a question
- Running a single command the user specified

---

## Required Sequence: Assess, Plan, Task, Execute

### Step 1: Assess Context

Before anything else, read the relevant context:

1. **Project state**: `CLAUDE.md` (architecture, conventions, non-negotiable rules)
2. **Auto memory**: Memory files in `.claude/projects/*/memory/` (past lessons, known pitfalls)
3. **Active plans**: `.claude/docs/scratchpads/` (if a plan exists for this work)
4. **Git status**: Unstaged changes, current branch, recent commits
5. **Affected modules**: Read the files you intend to modify before planning changes

**Purpose:** Understand what's been done, what patterns exist, and what constraints apply before planning any work.

**Do NOT skip this step.** Diving into implementation without reading context leads to mypy failures, broken tests, pattern violations, and wasted turns.

### Step 2: Build a Plan

For non-trivial work, create a plan before executing:

- **Multi-step tasks**: Use `EnterPlanMode` to produce a structured plan for user approval
- **Medium tasks** (3-5 clear steps): State the approach in a brief numbered list and confirm with the user before proceeding
- **Tasks with an existing plan file**: Read and follow the plan -- do not re-plan unless contradictions are found

**The plan must answer:**
1. What files will be created or modified?
2. What is the sequence of operations?
3. What are the dependencies between steps?
4. What verification will confirm success? (pytest, mypy --strict, ruff check)

### Step 3: Create TodoWrite Items

Before executing the first step, create a TodoWrite task list that:

- Breaks the plan into **specific, actionable items**
- Uses **imperative form** for content ("Add database migration") and **active form** for progress ("Adding database migration")
- Includes a final verification step (tests + type checking + linting)
- Has no more than **one task `in_progress`** at any time

**Example:**
```
1. Read existing worker_pool module and understand claim logic
2. Add new retry method to WorkerPool class
3. Write unit tests for retry behavior
4. Update integration tests for worker processing
5. Run pytest, mypy --strict, and ruff check
```

### Step 4: Execute Sequentially

- Work through TodoWrite items **one at a time**
- Mark each task **complete immediately** upon finishing (do not batch)
- If a blocker is discovered, **stop and reassess** -- do not push through
- If a file exceeds 400 lines during implementation, split it before continuing
- If mypy or ruff errors surface, fix them before moving to the next task

---

## Enforcement

Claude must self-check before writing code:

| Check | Required? |
|-------|-----------|
| Read relevant context and affected files | Yes, for all non-trivial tasks |
| Plan exists or was stated | Yes, for 3+ step tasks |
| TodoWrite items created | Yes, for 3+ step tasks |
| User approved approach | Yes, for ambiguous or multi-file changes |

**If any check fails, stop and complete it before proceeding.**

---

## Anti-Patterns (Hook-Enforced)

The following behaviors are enforced by hooks in `.claude/hooks/`. These are not advisory — they produce hard blocks or warnings at runtime.

### 1. TaskCreate Before Plan Approval — BLOCKED

**Hook:** `plan_mode_gate.sh` (PreToolUse → TaskCreate)

In execution or decision sessions, calling TaskCreate before completing the plan cycle (EnterPlanMode → plan → ExitPlanMode) is **hard-blocked** (exit 2). This enforces Step 2 of the required sequence above.

**Exempt:** Exploration and review sessions, or when no session type is set.

### 2. Multiple Tasks In-Progress — BLOCKED

**Hook:** `single_task_gate.sh` (PreToolUse → TaskUpdate)

Setting a second task to `in_progress` while another is already active is **hard-blocked**. This enforces the "one task at a time" rule from Step 3. Complete or delete the current task before starting the next.

**Idempotent:** Re-setting the same task to `in_progress` is allowed.

### 3. Stopping With Incomplete Tasks — WARNING

**Hook:** `task_stop_check.sh` (Stop)

When the session ends with a task still `in_progress`, a soft warning is emitted suggesting `/cc-handoff` to document the session. This is not a hard block to avoid infinite loops.

### 4. Available Slash Commands — HINT

**Hook:** `prompt_skill_detector.sh` (UserPromptSubmit)

When prompts contain keywords like "handoff", "commit", "review", or "test", the hook suggests the corresponding slash command (`/cc-handoff`, `/commit`, `/code-review`, `/quick-test`). These are informational hints, not blocks.

---

## Relationship to Other Rules

- **`security.md`**: Governs SQL safety, credential handling, and subprocess execution. Always applies during implementation.
- **`dev-patterns.md`**: Governs async patterns, parameterized SQL, optional SDK handling, and test conventions. Always applies during implementation.
- **`CLAUDE.md`**: Defines project conventions, file size limits, and non-negotiable rules. This task-execution rule operationalizes those constraints at the session level.
- **TodoWrite tool**: This rule formalizes when and how to use it -- not optional for non-trivial work.
