# Phase 3: Phase Gates + End-of-Run Validation (Revised)

> **Revised 2026-02-13** after Phase 2 completion (commit `eb393c0`).
> Original PHASE3.md replaced with actual metrics and 5 atomic sub-plans.

## Overview

| Attribute | Value |
|-----------|-------|
| **Goal** | Validate between phases and after complete runs |
| **Gaps addressed** | G4 (no phase gates), G5 (no end-of-run validation), G12 (no multi-phase loop), G13 (no CLI for manual validation) |
| **Pre-work** | Tech debt from Phase 2 (verify_only gap, _resolve_tool duplication) |
| **Dependencies** | Phase 2 COMPLETE (pipeline.py, verify_command, done_criteria all landed) |
| **Estimated sessions** | 5 (one per atomic plan) |
| **Risk level** | MEDIUM-HIGH -- 3A changes execution flow (phase gating) |
| **Produces for downstream** | `run_validator.py` integration surface for Phase 5 AC validation |

## Actual Baselines (Post-Phase 2)

| File | Lines | Notes |
|------|-------|-------|
| `worker_pool/pipeline.py` | 442 | TDD pipeline + `_run_post_verify_checks()` at 6 success paths |
| `worker_pool/worker.py` | 426 | Stable, no Phase 3 changes expected |
| `worker_pool/pool.py` | 179 | Only `run_parallel_phase()` -- no multi-phase loop |
| `worker_pool/verify_only.py` | 77 | Missing post-verify checks (gap found in Phase 2) |
| `worker_pool/verify_command_runner.py` | 155 | New in Phase 2 |
| `worker_pool/done_criteria_checker.py` | 177 | New in Phase 2 |
| `code_verifier.py` | 338 | `_resolve_tool()` duplicated in verify_command_runner |
| `cli.py` | 270 | Baseline for `--all-phases` and `validate` commands |
| `schema/schema.sql` | 748 | execution_runs needs validation columns |

## What Changed from Original PHASE3.md

| Area | Original Estimate | Actual | Impact |
|------|-------------------|--------|--------|
| pipeline.py baseline | ~430 | 442 | Closer to split threshold; monitor in 3A/3B |
| worker.py baseline | ~415 | 426 | No impact (Phase 3 doesn't touch worker.py) |
| verify_only.py gap | Not identified | 77 lines, missing post-verify checks | New pre-work task (03-00) |
| _resolve_tool() duplication | Not identified | 5-line function in 2 files | New pre-work task (03-00) |
| done_criteria integration | "results feed into run validation" | Log-only, no DB persistence | 3B aggregates from log, not DB |
| Session count | 5 | 5 (renamed: 03-00 through 03-04) | Pre-work added but CLI session consolidated |

## Atomic Plan Index

| Plan | Session | Scope | Gap |
|------|---------|-------|-----|
| [03-00-PLAN.md](03-00-PLAN.md) | 1 | Tech debt cleanup (pre-Phase 3) | -- |
| [03-01-PLAN.md](03-01-PLAN.md) | 2 | Multi-phase loop + CLI flag (3-Pre, G12) | G12 |
| [03-02-PLAN.md](03-02-PLAN.md) | 3 | Phase gate validator (3A) | G4 |
| [03-03-PLAN.md](03-03-PLAN.md) | 4 | End-of-run validator (3B) | G5 |
| [03-04-PLAN.md](03-04-PLAN.md) | 5 | CLI validate commands + regression (3C) | G13 |

## Line Count Projections

| File | Now | Post-00 | Post-01 | Post-02 | Post-03 | Post-04 |
|------|-----|---------|---------|---------|---------|---------|
| pool.py | 179 | 179 | ~255 | ~285 | ~300 | 300 |
| cli.py | 270 | 270 | ~285 | 285 | 285 | ~330 |
| pipeline.py | 442 | 442 | 442 | 442 | 442 | 442 |
| verify_only.py | 77 | ~88 | 88 | 88 | 88 | 88 |
| NEW phase_gate.py | -- | -- | -- | ~200 | 200 | 200 |
| NEW run_validator.py | -- | -- | -- | -- | ~200 | 200 |
| NEW subprocess_utils.py | -- | ~15 | 15 | 15 | 15 | 15 |

All files well under 800-line limit. pool.py reaches ~300 at peak (under 400 threshold).

## Integration Checklist

- [ ] verify_only.py calls post-verify checks (03-00)
- [ ] _resolve_tool() extracted to shared module (03-00)
- [ ] `run_all_phases()` processes all pending phases in order (03-01)
- [ ] `--all-phases` CLI flag triggers multi-phase loop (03-01)
- [ ] Phase gates run between phases and block on failure (03-02)
- [ ] `enable_phase_gates` config flag can disable gates (03-02)
- [ ] Phase gate re-runs individual test files on batch failure (03-02)
- [ ] Regression check catches prior phase breakage (03-02)
- [ ] End-of-run validation runs full regression + lint + type check (03-03)
- [ ] Validation results stored in `execution_runs` table (03-03)
- [ ] `validation_status` and `validation_details` columns exist (03-03)
- [ ] CLI `validate --phase N` runs phase gate (03-04)
- [ ] CLI `validate --run` runs end-of-run validation (03-04)
- [ ] CLI `validate --all` runs all gates + run validation (03-04)
- [ ] Existing single-phase execution path works unchanged (03-01)
- [ ] pool.py under 400 lines (03-03)
- [ ] cli.py under 400 lines (03-04)
- [ ] mypy strict clean, ruff clean, full unit suite passes (all)

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Phase gate too strict | Execution blocked unnecessarily | Config flag to disable; batch failure triggers individual re-runs |
| Phase gate too lenient | Broken phase cascades | Gate checks ALL test files; regression on prior phases |
| Multi-phase loop new failure modes | Execution hangs | Existing single-phase path unchanged; new path opt-in via `--all-phases` |
| Schema migration breaks data | DB errors | `ALTER TABLE ADD COLUMN` additive only; NULL for existing rows |
| pipeline.py growth | Approaches split threshold | Monitor; extract `_run_green_with_retry` if needed |
