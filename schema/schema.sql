-- Code-as-Orchestrator SQLite Schema
-- Version: 1.0 (POC Simplified)
-- Date: 2026-01-11
--
-- This schema tracks TDD task execution with full audit trail.
-- All state changes are persisted immediately for crash recovery.

-- =============================================================================
-- SPECIFICATIONS
-- Source documents from which tasks are decomposed (immutable after import)
-- =============================================================================

CREATE TABLE IF NOT EXISTS specs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,              -- e.g., "salesforce-v2"
    source_file TEXT NOT NULL,              -- e.g., "app_spec_v2.txt"
    content TEXT NOT NULL,                  -- Full specification text
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- =============================================================================
-- TASKS
-- Individual TDD tasks decomposed from specifications
-- =============================================================================

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spec_id INTEGER REFERENCES specs(id),

    -- Identity
    task_key TEXT NOT NULL UNIQUE,          -- e.g., "TDD-0A", "TDD-1"
    title TEXT NOT NULL,                    -- e.g., "Input Validation"

    -- Requirements
    goal TEXT,                              -- What this task accomplishes
    acceptance_criteria TEXT,               -- JSON array of testable criteria

    -- File paths
    test_file TEXT,                         -- e.g., "backend/tests/unit/sf/test_security.py"
    impl_file TEXT,                         -- e.g., "backend/src/integrations/sf/security.py"

    -- Verification
    verify_command TEXT,                    -- Shell command to verify completion (e.g., "uv run pytest tests/test_jwt.py -v")
    done_criteria TEXT,                     -- Human-readable success criteria (e.g., "JWT tokens generate correctly")

    -- Dependencies
    depends_on TEXT DEFAULT '[]',           -- JSON array of task_keys: ["TDD-0A"]

    -- Status lifecycle
    status TEXT DEFAULT 'pending'
        CHECK(status IN (
            'pending',      -- Ready to start (if dependencies met)
            'in_progress',  -- Currently executing
            'passing',      -- Tests passing (simplified for POC)
            'complete',     -- Successfully finished
            'blocked',      -- Cannot proceed (max retries exceeded)
            'blocked-static-review'  -- Static review violations unfixable
        )),

    -- Ordering
    phase INTEGER NOT NULL DEFAULT 0,       -- 0=foundation, 1=config, 2=core, etc.
    sequence INTEGER NOT NULL DEFAULT 0,    -- Order within phase

    -- Parallel execution (worker claiming)
    claimed_by INTEGER,                     -- References workers(id)
    claimed_at TIMESTAMP,                   -- When task was claimed
    claim_expires_at TIMESTAMP,             -- When claim auto-expires
    version INTEGER NOT NULL DEFAULT 1,     -- Optimistic locking version

    -- Complexity tracking (PLAN8)
    -- NOTE: For existing databases, manually run:
    --   ALTER TABLE tasks ADD COLUMN complexity TEXT DEFAULT 'medium'
    --       CHECK(complexity IN ('low', 'medium', 'high'));
    --   ALTER TABLE tasks ADD COLUMN implementation_hints TEXT;
    complexity TEXT DEFAULT 'medium'
        CHECK(complexity IN ('low', 'medium', 'high')),
    implementation_hints TEXT,           -- JSON with hints from Pass 4

    -- PLAN9: Module exports for scaffolding reference
    module_exports TEXT DEFAULT '[]',    -- JSON array of export names

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- =============================================================================
-- ATTEMPTS
-- Every attempt to complete a stage (full execution history)
-- =============================================================================

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id),

    -- Stage identification
    stage TEXT NOT NULL
        CHECK(stage IN ('red', 'red_fix', 'green', 'review', 'fix', 'verify', 're_verify', 'refactor', 'commit')),
    attempt_number INTEGER NOT NULL,        -- 1, 2, 3... per stage

    -- Prompt tracking (for debugging and deduplication)
    prompt_hash TEXT,                       -- SHA256 prefix of prompt sent

    -- Timing
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    duration_ms INTEGER,

    -- Result
    success INTEGER,                        -- 0=failed, 1=success
    error_message TEXT,                     -- Failure reason if not success

    -- Files affected
    files_created TEXT DEFAULT '[]',        -- JSON array of paths
    files_modified TEXT DEFAULT '[]',       -- JSON array of paths

    -- LLM response (for debugging)
    llm_response_preview TEXT,              -- First 1000 chars of response

    -- Verification outputs (code-verified results)
    pytest_exit_code INTEGER,
    pytest_output TEXT,                     -- Truncated output
    mypy_exit_code INTEGER,
    mypy_output TEXT,
    ruff_exit_code INTEGER,
    ruff_output TEXT,

    -- Complexity tracking (PLAN8)
    -- NOTE: For existing databases, manually run:
    --   ALTER TABLE attempts ADD COLUMN prompt_enhanced INTEGER DEFAULT 0;
    prompt_enhanced INTEGER DEFAULT 0       -- 1 if hints were added to prompt
);


-- =============================================================================
-- WORKERS
-- Registry of worker processes for parallel execution
-- =============================================================================

CREATE TABLE IF NOT EXISTS workers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    worker_id INTEGER UNIQUE NOT NULL,      -- PID or unique worker identifier
    status TEXT NOT NULL DEFAULT 'idle'
        CHECK(status IN ('active', 'idle', 'dead')),
    registered_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_heartbeat TIMESTAMP,               -- Last successful heartbeat
    current_task_id INTEGER,                -- Task currently being worked on
    branch_name TEXT,                       -- Git branch for this worker
    FOREIGN KEY (current_task_id) REFERENCES tasks(id)
);


-- =============================================================================
-- WORKER HEARTBEATS
-- Append-only log of worker health signals
-- =============================================================================

CREATE TABLE IF NOT EXISTS worker_heartbeats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    worker_id INTEGER NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL,                   -- Worker status at heartbeat time
    task_id INTEGER,                        -- Task being worked on (if any)
    FOREIGN KEY (worker_id) REFERENCES workers(id),
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);


-- =============================================================================
-- EXECUTION RUNS
-- Session tracking for orchestration runs
-- =============================================================================

CREATE TABLE IF NOT EXISTS execution_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    total_invocations INTEGER DEFAULT 0,    -- API invocations in this run
    max_workers INTEGER,                    -- Max concurrent workers used
    status TEXT NOT NULL DEFAULT 'running'
        CHECK(status IN ('running', 'completed', 'failed', 'cancelled', 'passed'))
);


-- =============================================================================
-- INVOCATIONS
-- Track API/LLM invocations for budget management
-- =============================================================================

CREATE TABLE IF NOT EXISTS invocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    worker_id INTEGER,                      -- Worker that made the invocation
    task_id INTEGER,                        -- Task context (if any)
    stage TEXT NOT NULL,                    -- Stage: red, green, review, etc.
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    token_count INTEGER,                    -- Tokens used (if available)
    duration_ms INTEGER,                    -- Duration in milliseconds
    FOREIGN KEY (run_id) REFERENCES execution_runs(id),
    FOREIGN KEY (worker_id) REFERENCES workers(id),
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);


-- =============================================================================
-- TASK CLAIMS
-- Audit log for task claiming/releasing
-- =============================================================================

CREATE TABLE IF NOT EXISTS task_claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    worker_id INTEGER NOT NULL,
    claimed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    released_at TIMESTAMP,                  -- When claim was released
    outcome TEXT                            -- How the claim ended
        CHECK(outcome IS NULL OR outcome IN ('completed', 'failed', 'timeout', 'released')),
    FOREIGN KEY (task_id) REFERENCES tasks(id),
    FOREIGN KEY (worker_id) REFERENCES workers(id)
);


-- =============================================================================
-- CONFIGURATION
-- Runtime configuration (quality thresholds, etc.)
-- =============================================================================

CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Default configuration values
INSERT OR IGNORE INTO config (key, value, description) VALUES
    ('max_green_attempts', '3', 'Maximum GREEN phase retries'),
    ('max_fix_attempts', '3', 'Maximum fix loop iterations'),
    ('claude_timeout', '300', 'Claude CLI timeout in seconds'),
    ('claude_model', 'sonnet', 'Claude model to use'),
    -- Parallel execution configuration
    ('max_workers', '2', 'Maximum concurrent worker processes'),
    ('max_invocations_per_session', '100', 'Budget limit for API invocations per session'),
    ('budget_warning_threshold', '80', 'Percentage of budget that triggers warning'),
    ('heartbeat_interval_seconds', '30', 'Worker heartbeat interval'),
    ('claim_timeout_seconds', '300', 'Task claim expiration timeout');


-- =============================================================================
-- MODULE EXPORTS AUDIT (PLAN9)
-- Audit log for module_exports changes
-- =============================================================================

CREATE TABLE IF NOT EXISTS module_exports_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_key TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    action TEXT NOT NULL CHECK(action IN ('backfill', 'migration', 'manual_update', 'decomposition')),
    old_value TEXT,
    new_value TEXT,
    reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_module_exports_audit_task_key ON module_exports_audit(task_key);
CREATE INDEX IF NOT EXISTS idx_module_exports_audit_timestamp ON module_exports_audit(timestamp);


-- =============================================================================
-- INDEXES
-- Optimize common queries
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_spec_id ON tasks(spec_id);
CREATE INDEX IF NOT EXISTS idx_tasks_phase_seq ON tasks(phase, sequence);
CREATE INDEX IF NOT EXISTS idx_tasks_claimed_by ON tasks(claimed_by);
CREATE INDEX IF NOT EXISTS idx_tasks_claim_expires ON tasks(claim_expires_at);
CREATE INDEX IF NOT EXISTS idx_tasks_complexity ON tasks(complexity);  -- PLAN8: Complexity queries
CREATE INDEX IF NOT EXISTS idx_attempts_task_id ON attempts(task_id);
CREATE INDEX IF NOT EXISTS idx_attempts_stage ON attempts(stage);
CREATE INDEX IF NOT EXISTS idx_attempts_task_stage ON attempts(task_id, stage);

-- Parallel execution indexes
CREATE INDEX IF NOT EXISTS idx_workers_status ON workers(status);
CREATE INDEX IF NOT EXISTS idx_workers_last_heartbeat ON workers(last_heartbeat);
CREATE INDEX IF NOT EXISTS idx_worker_heartbeats_worker ON worker_heartbeats(worker_id);
CREATE INDEX IF NOT EXISTS idx_worker_heartbeats_timestamp ON worker_heartbeats(timestamp);
CREATE INDEX IF NOT EXISTS idx_invocations_run ON invocations(run_id);
CREATE INDEX IF NOT EXISTS idx_invocations_worker ON invocations(worker_id);
CREATE INDEX IF NOT EXISTS idx_invocations_task ON invocations(task_id);
CREATE INDEX IF NOT EXISTS idx_task_claims_task ON task_claims(task_id);
CREATE INDEX IF NOT EXISTS idx_task_claims_worker ON task_claims(worker_id);
CREATE INDEX IF NOT EXISTS idx_execution_runs_status ON execution_runs(status);


-- =============================================================================
-- TRIGGERS
-- Maintain data integrity
-- =============================================================================

-- Update tasks.updated_at on any status change
CREATE TRIGGER IF NOT EXISTS trg_task_updated
AFTER UPDATE OF status ON tasks
BEGIN
    UPDATE tasks SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;


-- =============================================================================
-- VIEWS
-- Convenience views for common queries
-- =============================================================================

-- Task status summary
CREATE VIEW IF NOT EXISTS v_status_summary AS
SELECT
    status,
    COUNT(*) as count,
    GROUP_CONCAT(task_key) as task_keys
FROM tasks
GROUP BY status;

-- Ready tasks (pending with dependencies met)
CREATE VIEW IF NOT EXISTS v_ready_tasks AS
SELECT t.*
FROM tasks t
WHERE t.status = 'pending'
AND NOT EXISTS (
    SELECT 1
    FROM json_each(t.depends_on) AS dep
    JOIN tasks blocker ON blocker.task_key = dep.value
    WHERE blocker.status NOT IN ('complete', 'passing')
)
ORDER BY t.phase, t.sequence;

-- Claimable tasks (ready tasks not claimed or with expired claims)
CREATE VIEW IF NOT EXISTS v_claimable_tasks AS
SELECT t.*
FROM v_ready_tasks t
WHERE t.claimed_by IS NULL
   OR t.claim_expires_at < CURRENT_TIMESTAMP
ORDER BY t.phase, t.sequence;

-- Stale tasks (tasks with expired claims that need recovery)
CREATE VIEW IF NOT EXISTS v_stale_tasks AS
SELECT
    t.*,
    w.worker_id AS claiming_worker_id,
    w.status AS worker_status
FROM tasks t
LEFT JOIN workers w ON t.claimed_by = w.id
WHERE t.claim_expires_at IS NOT NULL
  AND t.claim_expires_at < CURRENT_TIMESTAMP
  AND t.status = 'in_progress';

-- Stale workers (no heartbeat for 10+ minutes)
CREATE VIEW IF NOT EXISTS v_stale_workers AS
SELECT
    w.*,
    t.task_key AS current_task_key,
    CAST((julianday(CURRENT_TIMESTAMP) - julianday(w.last_heartbeat)) * 24 * 60 AS INTEGER) AS minutes_since_heartbeat
FROM workers w
LEFT JOIN tasks t ON w.current_task_id = t.id
WHERE w.status != 'dead'
  AND (
    w.last_heartbeat IS NULL
    OR (julianday(CURRENT_TIMESTAMP) - julianday(w.last_heartbeat)) * 24 * 60 > 10
  );

-- Worker statistics
CREATE VIEW IF NOT EXISTS v_worker_stats AS
SELECT
    w.id,
    w.worker_id,
    w.status,
    w.registered_at,
    w.last_heartbeat,
    w.branch_name,
    t.task_key AS current_task,
    (SELECT COUNT(*) FROM task_claims tc WHERE tc.worker_id = w.id) AS total_claims,
    (SELECT COUNT(*) FROM task_claims tc WHERE tc.worker_id = w.id AND tc.outcome = 'completed') AS completed_claims,
    (SELECT COUNT(*) FROM task_claims tc WHERE tc.worker_id = w.id AND tc.outcome = 'failed') AS failed_claims,
    (SELECT COUNT(*) FROM invocations i WHERE i.worker_id = w.id) AS total_invocations
FROM workers w
LEFT JOIN tasks t ON w.current_task_id = t.id;


-- =============================================================================
-- CIRCUIT BREAKERS (PLAN2)
-- Track circuit breaker state at all levels
-- =============================================================================

CREATE TABLE IF NOT EXISTS circuit_breakers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identity
    level TEXT NOT NULL
        CHECK(level IN ('stage', 'worker', 'system')),
    identifier TEXT NOT NULL,              -- task_id:stage, worker_id, or 'system'

    -- Run association
    run_id INTEGER,                        -- FK to execution_runs for context

    -- State
    state TEXT NOT NULL DEFAULT 'closed'
        CHECK(state IN ('closed', 'open', 'half_open')),

    -- Optimistic locking
    version INTEGER NOT NULL DEFAULT 1,    -- Increment on each update

    -- Counters
    failure_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    half_open_requests INTEGER NOT NULL DEFAULT 0,
    extensions_count INTEGER NOT NULL DEFAULT 0,

    -- Timestamps
    last_failure_at TEXT,
    last_success_at TEXT,
    opened_at TEXT,                        -- When circuit tripped
    last_state_change_at TEXT DEFAULT (datetime('now')),

    -- Configuration snapshot (JSON)
    config_snapshot TEXT,                  -- Captures config at creation

    -- Metadata
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),

    UNIQUE(level, identifier)
);

CREATE INDEX IF NOT EXISTS idx_circuit_breakers_level_state
    ON circuit_breakers(level, state);
CREATE INDEX IF NOT EXISTS idx_circuit_breakers_run_id
    ON circuit_breakers(run_id);

-- =============================================================================
-- CIRCUIT BREAKER EVENTS
-- Append-only audit log for all circuit breaker state changes
-- =============================================================================

CREATE TABLE IF NOT EXISTS circuit_breaker_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identity
    circuit_id INTEGER NOT NULL,           -- FK to circuit_breakers
    run_id INTEGER,                        -- FK to execution_runs

    -- Event details
    event_type TEXT NOT NULL
        CHECK(event_type IN (
            'state_change',                -- CLOSED->OPEN, OPEN->HALF_OPEN, etc.
            'failure_recorded',            -- Failure counter incremented
            'success_recorded',            -- Success counter incremented
            'threshold_reached',           -- Failure threshold met
            'recovery_started',            -- Half-open test initiated
            'recovery_succeeded',          -- Test passed, circuit closing
            'recovery_failed',             -- Test failed, circuit reopening
            'manual_reset',                -- Admin intervention
            'flapping_detected',           -- Circuit changing state rapidly
            'extension_applied'            -- Pause extended for worker
        )),

    -- State info
    from_state TEXT,                       -- Previous state (null for creation)
    to_state TEXT,                         -- New state

    -- Context (JSON)
    error_context TEXT,                    -- Error details, stack trace, etc.

    -- Audit
    created_at TEXT NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (circuit_id) REFERENCES circuit_breakers(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_circuit_breaker_events_circuit_id
    ON circuit_breaker_events(circuit_id);
CREATE INDEX IF NOT EXISTS idx_circuit_breaker_events_created_at
    ON circuit_breaker_events(created_at);
CREATE INDEX IF NOT EXISTS idx_circuit_breaker_events_event_type
    ON circuit_breaker_events(event_type);

-- =============================================================================
-- FAILURE COUNTS (for sliding window mode)
-- Time-bucketed failure counts for advanced failure tracking
-- =============================================================================

CREATE TABLE IF NOT EXISTS failure_counts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identity
    circuit_id INTEGER NOT NULL,           -- FK to circuit_breakers

    -- Time bucket (for sliding window calculations)
    bucket_start TEXT NOT NULL,            -- Start of time bucket
    bucket_end TEXT NOT NULL,              -- End of time bucket

    -- Counts
    failure_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,

    -- Metadata
    created_at TEXT NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (circuit_id) REFERENCES circuit_breakers(id) ON DELETE CASCADE,
    UNIQUE(circuit_id, bucket_start)
);

CREATE INDEX IF NOT EXISTS idx_failure_counts_circuit_bucket
    ON failure_counts(circuit_id, bucket_start);

-- =============================================================================
-- CIRCUIT BREAKER VIEWS
-- Optimized views for monitoring (no correlated subqueries)
-- =============================================================================

-- Active open circuits requiring attention
CREATE VIEW IF NOT EXISTS v_open_circuits AS
SELECT
    cb.id,
    cb.level,
    cb.identifier,
    cb.state,
    cb.failure_count,
    cb.opened_at,
    cb.extensions_count,
    CAST((julianday('now') - julianday(cb.opened_at)) * 24 * 60 AS INTEGER) AS minutes_open
FROM circuit_breakers cb
WHERE cb.state IN ('open', 'half_open')
ORDER BY cb.opened_at ASC;

-- Flapping circuits (>5 state changes in 5 minutes)
CREATE VIEW IF NOT EXISTS v_flapping_circuits AS
SELECT
    cb.id,
    cb.level,
    cb.identifier,
    cb.state,
    COUNT(cbe.id) AS state_changes_5min
FROM circuit_breakers cb
JOIN circuit_breaker_events cbe ON cbe.circuit_id = cb.id
WHERE cbe.event_type = 'state_change'
  AND cbe.created_at >= datetime('now', '-5 minutes')
GROUP BY cb.id, cb.level, cb.identifier, cb.state
HAVING COUNT(cbe.id) > 5;

-- Circuit health summary by level
CREATE VIEW IF NOT EXISTS v_circuit_health_summary AS
SELECT
    level,
    COUNT(*) AS total_circuits,
    SUM(CASE WHEN state = 'closed' THEN 1 ELSE 0 END) AS closed_count,
    SUM(CASE WHEN state = 'open' THEN 1 ELSE 0 END) AS open_count,
    SUM(CASE WHEN state = 'half_open' THEN 1 ELSE 0 END) AS half_open_count
FROM circuit_breakers
GROUP BY level;

-- Complete status of all circuits
CREATE VIEW IF NOT EXISTS v_circuit_breaker_status AS
SELECT
    cb.id,
    cb.level,
    cb.identifier,
    cb.state,
    cb.failure_count,
    cb.success_count,
    cb.extensions_count,
    cb.opened_at,
    cb.last_failure_at,
    cb.last_success_at,
    cb.last_state_change_at,
    cb.version,
    cb.run_id
FROM circuit_breakers cb
ORDER BY cb.level, cb.identifier;

-- Notification history view (for throttling checks)
CREATE VIEW IF NOT EXISTS v_notification_history AS
SELECT
    cbe.id,
    cb.level,
    cb.identifier,
    cbe.event_type,
    cbe.from_state,
    cbe.to_state,
    cbe.created_at
FROM circuit_breaker_events cbe
JOIN circuit_breakers cb ON cbe.circuit_id = cb.id
WHERE cbe.event_type IN ('state_change', 'flapping_detected', 'manual_reset')
ORDER BY cbe.created_at DESC
LIMIT 100;

-- Time to recovery metrics (open->closed duration)
CREATE VIEW IF NOT EXISTS v_time_to_recovery AS
SELECT
    cb.id,
    cb.level,
    cb.identifier,
    open_event.created_at AS opened_at,
    close_event.created_at AS closed_at,
    CAST(
        (julianday(close_event.created_at) - julianday(open_event.created_at)) * 24 * 60
        AS INTEGER
    ) AS recovery_minutes
FROM circuit_breakers cb
JOIN circuit_breaker_events open_event ON open_event.circuit_id = cb.id
    AND open_event.event_type = 'state_change'
    AND open_event.to_state = 'open'
JOIN circuit_breaker_events close_event ON close_event.circuit_id = cb.id
    AND close_event.event_type = 'state_change'
    AND close_event.to_state = 'closed'
    AND close_event.created_at > open_event.created_at
WHERE NOT EXISTS (
    -- Ensure no intermediate open event between this open and close
    SELECT 1 FROM circuit_breaker_events middle
    WHERE middle.circuit_id = cb.id
      AND middle.event_type = 'state_change'
      AND middle.to_state = 'open'
      AND middle.created_at > open_event.created_at
      AND middle.created_at < close_event.created_at
);


-- =============================================================================
-- CIRCUIT BREAKER TRIGGERS
-- =============================================================================

-- Auto-update updated_at timestamp
CREATE TRIGGER IF NOT EXISTS trg_circuit_breakers_updated_at
AFTER UPDATE ON circuit_breakers
BEGIN
    UPDATE circuit_breakers
    SET updated_at = datetime('now')
    WHERE id = NEW.id;
END;


-- =============================================================================
-- AST CODE QUALITY VIOLATIONS (PLAN3)
-- Track AST violations detected during code quality checks
-- =============================================================================

CREATE TABLE IF NOT EXISTS ast_violations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    impl_file TEXT NOT NULL,
    pattern TEXT NOT NULL,
    line_number INTEGER NOT NULL,
    message TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'error',
    metadata TEXT,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks (id)
);

-- Index for efficient querying by task
CREATE INDEX IF NOT EXISTS idx_ast_violations_task_id ON ast_violations(task_id);


-- =============================================================================
-- GIT STASH OPERATION LOG (PLAN3)
-- Track git stash operations for rollback protection
-- =============================================================================

CREATE TABLE IF NOT EXISTS git_stash_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    stash_id TEXT,
    operation TEXT NOT NULL,  -- 'create', 'drop', 'pop', 'skip'
    success BOOLEAN NOT NULL,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks (id)
);

-- Index for efficient querying by task
CREATE INDEX IF NOT EXISTS idx_git_stash_log_task_id ON git_stash_log(task_id);


-- =============================================================================
-- STATIC REVIEW METRICS (PLAN12 Phase 1B Shadow Mode)
-- Track Phase 1B warning rates for promotion decisions
-- =============================================================================

CREATE TABLE IF NOT EXISTS static_review_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Task context
    task_id INTEGER NOT NULL,
    task_key TEXT NOT NULL,
    run_id INTEGER,

    -- Check identification
    check_name TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'warning'
        CHECK(severity IN ('error', 'warning')),

    -- Violation details
    line_number INTEGER NOT NULL,
    message TEXT NOT NULL,
    code_snippet TEXT,
    fix_guidance TEXT,

    -- Outcome tracking (updated post-task completion)
    was_false_positive INTEGER,
    outcome_reason TEXT,
    outcome_recorded_at TEXT,

    -- Timestamps
    detected_at TEXT NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (task_id) REFERENCES tasks(id),
    FOREIGN KEY (run_id) REFERENCES execution_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_srm_task_id ON static_review_metrics(task_id);
CREATE INDEX IF NOT EXISTS idx_srm_check_name ON static_review_metrics(check_name);
CREATE INDEX IF NOT EXISTS idx_srm_severity ON static_review_metrics(severity);
CREATE INDEX IF NOT EXISTS idx_srm_detected_at ON static_review_metrics(detected_at);

-- View: Summary metrics for promotion decisions
CREATE VIEW IF NOT EXISTS v_shadow_mode_summary AS
SELECT
    check_name,
    COUNT(*) as total_warnings,
    COUNT(CASE WHEN was_false_positive IS NOT NULL THEN 1 END) as reviewed_count,
    SUM(CASE WHEN was_false_positive = 1 THEN 1 ELSE 0 END) as false_positive_count,
    SUM(CASE WHEN was_false_positive = 0 THEN 1 ELSE 0 END) as true_positive_count,
    CASE
        WHEN COUNT(CASE WHEN was_false_positive IS NOT NULL THEN 1 END) >= 20 THEN
            ROUND(100.0 * SUM(CASE WHEN was_false_positive = 1 THEN 1 ELSE 0 END) /
                  COUNT(CASE WHEN was_false_positive IS NOT NULL THEN 1 END), 2)
        ELSE NULL
    END as fp_rate_percent,
    MIN(detected_at) as first_detected,
    MAX(detected_at) as last_detected
FROM static_review_metrics
WHERE severity = 'warning'
GROUP BY check_name;
