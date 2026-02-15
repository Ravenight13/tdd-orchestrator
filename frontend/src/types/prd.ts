export interface PrdSubmitResponse {
  run_id: string
  status: string
  message: string
}

export interface PrdStatusResponse {
  run_id: string
  stage: string
  status: string
  task_count: number | null
  error_message: string | null
}
