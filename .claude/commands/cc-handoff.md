---
name: cc-handoff
description: Generates dual-file session handoff (SESSION + HANDOFF) from conversation context at end of work sessions to document accomplishments and prepare next steps
argument-hint: "[session-description] [--dry-run]"
allowed-tools:
  - Read
  - Write(.claude/docs/**)
  - Bash(mkdir -p *)
  - Bash(pwd *)
  - Bash(ls *)
  - Bash(date *)
  - Bash(git log *)
  - Bash(git status *)
  - Bash(git diff --stat *)
  - Bash(git add *)
  - Bash(git commit *)
---

<objective>
Generate dual-file handoff structure by analyzing conversation context:
- **SESSION file**: Comprehensive record of what happened (decisions, accomplishments)
  - Named after what was accomplished (e.g., `SESSION_2026-01-16_improved-circuit-breaker-thresholds.md`)
- **HANDOFF file**: Concise summary of what's next (priorities, quick start, blockers)
  - Named after the next action (e.g., `HANDOFF_2026-01-16_add-worker-health-metrics.md`)

Automates session documentation with semantic filenames that tell you at a glance what happened and what's next.

**Project**: TDD Orchestrator - Parallel TDD task execution engine with three-level circuit breakers.
</objective>

<quick_start>
Analyze conversation context to extract accomplishments and next priorities, then generate two files:
1. SESSION file (what happened) named for the accomplishment
2. HANDOFF file (what's next) named for the next action

SESSION files written to `.claude/docs/summaries/`, HANDOFF files written to `.claude/docs/handoffs/`.

Run `/cc-handoff` to auto-detect descriptions, or `/cc-handoff "description"` to specify the session milestone.
</quick_start>

<dynamic_context>
<timestamp>
date: !`date +%Y-%m-%d`
time_hhmm: !`date +%H%M`
time_full: !`date +%H:%M:%S`
timezone: !`date +%Z`
filename_ts: !`date +%Y-%m-%d_%H%M`
</timestamp>

<project_root>
!`pwd`
</project_root>

<session_dirs>
summaries: .claude/docs/summaries
handoffs: .claude/docs/handoffs
</session_dirs>

<project_state>
branch: !`git -C /Users/cliffclarke/Projects/tdd_orchestrator branch --show-current 2>/dev/null || echo "unknown"`
recent_commits: !`git -C /Users/cliffclarke/Projects/tdd_orchestrator log --oneline -5 2>/dev/null || echo "No commits"`
uncommitted: !`git -C /Users/cliffclarke/Projects/tdd_orchestrator status --short 2>/dev/null | head -5 || echo "Clean"`
</project_state>
</dynamic_context>

<timestamp_rules>
**CRITICAL: Timestamp Handling**

You MUST use the EXACT values from `<timestamp>` above. NEVER generate timestamps yourself.

- Date: Use the literal value from `date:` (e.g., `2026-01-16`)
- Time: Use the literal value from `time_full:` (e.g., `10:13:45`)
- Timezone: Use the literal value from `timezone:` (e.g., `CST`)
- Filename timestamp: Use the literal value from `filename_ts:` (e.g., `2026-01-16_1013`)

Claude's internal clock is unreliable and does not know the user's timezone.
</timestamp_rules>

<workflow>
<step name="parse_input">
**Determine milestone descriptions:**

- If `$ARGUMENTS` contains `--dry-run`, set dry_run=true and remove flag from arguments

**Generate TWO descriptions by analyzing conversation:**

1. **SESSION description** (what happened - past tense):
   - What was the main accomplishment?
   - Examples: "Improved circuit breaker thresholds", "Added worker health metrics", "Fixed claim expiration bug"

2. **HANDOFF description** (what's next - action-oriented):
   - What is the immediate next step?
   - Examples: "Add worker health metrics", "Test multi-branch mode", "Implement decomposition caching"

**Generate slugs:** Lowercase, replace spaces/special chars with hyphens.

**If `$ARGUMENTS` provided:** Use as SESSION description, then infer HANDOFF from next priorities.
</step>

<step name="extract_content">
**Analyze this conversation to extract:**

1. **Executive Summary** (2-3 sentences)
2. **Accomplishments** (3-5 bullet points)
3. **Key Decisions** (optional - omit section if none)
4. **Known Issues / Blockers** (optional - omit section if none)
5. **Next Priorities** (1-3 items, formatted as dispatchable tasks)
6. **Files Modified** (list from git status and conversation)
</step>

<step name="write_files">
**Write files directly (no confirmation needed):**

1. Ensure directories exist:
   ```bash
   mkdir -p ".claude/docs/summaries" ".claude/docs/handoffs"
   ```

2. Write SESSION file to `.claude/docs/summaries/`
3. Write HANDOFF file to `.claude/docs/handoffs/`

**If --dry-run flag was set:** Show templates and detected paths but skip file creation.
</step>

<step name="commit_handoff">
**Create a conventional commit with the handoff files:**

1. Stage both files:
   ```bash
   git add ".claude/docs/summaries/SESSION_{filename_ts}_{session_slug}.md" ".claude/docs/handoffs/HANDOFF_{filename_ts}_{handoff_slug}.md"
   ```

2. Also stage any other uncommitted work from this session (check `git status` for modified/new files related to session work). Use your judgement — only include files that were part of this session's work, not unrelated changes.

3. Create a conventional commit:
   ```bash
   git commit -m "chore(session): {session_slug}

   Session: {session_description}
   Handoff: {handoff_description}

   Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
   ```

**Conventional commit rules:**
- Type is always `chore` for session handoffs
- Scope is always `session`
- Subject uses the session slug (lowercase, hyphenated)
- Body includes both session and handoff descriptions for context

**If --dry-run:** Skip this step entirely.
</step>

<step name="confirm_success">
**After committing:**

```
Session handoff complete!

Project: TDD Orchestrator

Files written:
  SESSION: .claude/docs/summaries/SESSION_{filename_ts}_{session_slug}.md
  HANDOFF: .claude/docs/handoffs/HANDOFF_{filename_ts}_{handoff_slug}.md

Committed: chore(session): {session_slug}

Named for what happened: "{session_description}"
Named for what's next: "{handoff_description}"
```
</step>
</workflow>

<templates>
<session_template name="SESSION" purpose="comprehensive - what happened">
```markdown
---
session_date: {date}
session_time: {time_full}
status: {session_description}
branch: {branch}
tags: [session-complete, tdd-orchestrator]
---

# Session: {session_description}

**Date**: {date} | **Time**: {time_full} {timezone}

---

## Executive Summary

{executive_summary}

---

## Key Decisions

{key_decisions OR "_No major decisions this session_"}

---

## Completed Work

### Accomplishments

{accomplishments as bullet points}

### Files Modified

{list of files created or updated during this session}

### Git State

- **Branch**: {branch}
- **Recent commits**: {relevant commits from this session}
- **Uncommitted changes**: {uncommitted or "None"}

---

## Known Issues

{known_issues OR "None"}

---

## Next Priorities

{next_priorities as numbered list}

---

*Session logged: {date} {time_full} {timezone}*
```
</session_template>

<handoff_template name="HANDOFF" purpose="concise - what's next">
```markdown
---
session_date: {date}
session_time: {time_full}
status: {handoff_description}
branch: {branch}
tags: [session-complete, tdd-orchestrator]
---

# Handoff: {handoff_description}

**Date**: {date} | **Time**: {time_full} {timezone}

---

## Resume Checklist

Before starting, review:
1. This handoff document
2. Recent git log: `git log --oneline -10`
3. Run health check: `/cc-ready`

```bash
# Quick health check
cd /Users/cliffclarke/Projects/tdd_orchestrator
python -m pytest tests/unit/ --tb=no -q
python -m ruff check src/
python -m mypy src/ --strict
```

---

## Executive Summary

{executive_summary}

---

## Current State

- **Branch**: {branch}
- **Known issues**: {known_issues OR "None"}
- **Uncommitted changes**: {uncommitted or "None"}

---

## Next Priorities

{next_priorities as numbered list}

---

## Key Context

- **Full session log**: `.claude/docs/summaries/SESSION_{filename_ts}_{session_slug}.md`
- **CLAUDE.md**: Project conventions and rules
- **Architecture**: `docs/ARCHITECTURE.md`

---

*Handoff created: {date} {time_full} {timezone}*
```
</handoff_template>
</templates>

<validation>
Before writing files, verify inputs:
- [ ] Session description is non-empty (what happened - past tense)
- [ ] Handoff description is non-empty (what's next - action-oriented)
- [ ] Both slugs contain only lowercase letters, numbers, and hyphens
- [ ] At least one accomplishment extracted from conversation
- [ ] At least one next priority identified
- [ ] Timestamps use exact values from `<timestamp>` section (never self-generated)
</validation>

<error_handling>
- **Non-git directory**: Skip git state sections. Use "N/A" for branch and commit fields.
- **Empty conversation**: Ask user for session description rather than generating empty files.
- **Invalid --dry-run placement**: Strip `--dry-run` flag from any position in $ARGUMENTS.
- **Directory creation failure**: Report error with path and permissions context.
- **Missing timestamp values**: If any dynamic command substitution returns empty, halt and report which timestamp failed.
</error_handling>

<success_criteria>
Task is complete when:
- SESSION file created in `.claude/docs/summaries/`, HANDOFF file created in `.claude/docs/handoffs/`
- Filenames use correct timestamp format from `<timestamp>` and semantic slugs
- SESSION contains comprehensive record (summary, decisions, accomplishments, files modified, git state)
- HANDOFF contains concise next-step guidance (resume checklist, priorities, context links)
- No placeholder text remains in generated files
- Conventional commit created: `chore(session): {session_slug}`
- Confirmation message displays both file paths and commit info
</success_criteria>

<examples>
```bash
# Infer both descriptions from conversation (recommended)
/cc-handoff

# With explicit session description
/cc-handoff "Fixed circuit breaker race condition"

# Preview only (no files created)
/cc-handoff --dry-run
```
</examples>
