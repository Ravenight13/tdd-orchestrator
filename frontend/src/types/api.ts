import type {
  TaskStatus,
  Complexity,
  CircuitLevel,
  CircuitState,
  RunStatus,
} from './domain'

// --- Tasks ---

export interface TaskSummary {
  id: string
  title: string
  status: TaskStatus
  phase: number
  sequence: number
  complexity: Complexity
}

export interface TaskListResponse {
  tasks: TaskSummary[]
  total: number
  limit: number
  offset: number
}

export interface TaskStats {
  pending: number
  running: number
  passed: number
  failed: number
  total: number
}

export interface TaskProgress {
  total: number
  completed: number
  percentage: number
  by_status: Record<TaskStatus, number>
}

export interface Attempt {
  id: number
  stage: string
  attempt_number: number
  success: boolean
  error_message: string | null
  started_at: string | null
}

export interface TaskDetail {
  id: string
  title: string
  status: TaskStatus
  phase: number
  sequence: number
  complexity: Complexity
  attempts: Attempt[]
}

export interface RetryResponse {
  task_key: string
  status: 'pending'
}

// --- Workers ---

export interface Worker {
  id: string
  status: string
  registered_at: string
  last_heartbeat: string | null
  current_task_id: number | null
  branch_name: string | null
}

export interface WorkerListResponse {
  workers: Worker[]
  total: number
}

export interface StaleWorker extends Worker {
  minutes_since_heartbeat: number | null
  current_task_key: string | null
}

export interface StaleWorkersResponse {
  items: StaleWorker[]
  total: number
}

// --- Circuits ---

export interface CircuitHealthSummary {
  level: CircuitLevel
  total_circuits: number
  closed_count: number
  open_count: number
  half_open_count: number
}

export type CircuitHealthResponse = CircuitHealthSummary[]

export interface CircuitBreakerDetail {
  id: string
  level: CircuitLevel
  identifier: string
  state: CircuitState
  failure_count: number
  success_count: number
  extensions_count: number
  opened_at: string | null
  last_failure_at: string | null
  last_success_at: string | null
  last_state_change_at: string | null
  version: number
  run_id: number | null
}

export interface CircuitBreakerListResponse {
  circuits: CircuitBreakerDetail[]
  total: number
}

// --- Runs ---

export interface Run {
  id: string
  task_id: string | null
  status: RunStatus
  started_at: string
  worker_id: string | null
}

export interface RunListResponse {
  runs: Run[]
  total: number
}

// --- Metrics ---

export interface MetricsJson {
  pending_count: number
  running_count: number
  passed_count: number
  failed_count: number
  total_count: number
  avg_duration_seconds: number | null
}
