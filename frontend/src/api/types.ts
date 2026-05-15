export type HealthResponse = {
  status: string;
  service: string;
};

export type ColumnProfile = {
  name: string;
  inferred_type: "date" | "number" | "string" | "boolean" | "unknown";
  null_rate: number;
  sample_values: unknown[];
};

export type CsvProfile = {
  upload_id: string;
  filename: string;
  storage_path: string;
  row_count: number;
  columns: ColumnProfile[];
  detected: {
    time_candidates: string[];
    kpi_candidates: string[];
    media_activity_candidates: Array<{ column: string; channel: string }>;
    spend_channel_candidates: Array<{ column: string; channel: string }>;
    revenue_candidates: string[];
    control_candidates: string[];
    geo_candidates: string[];
    population_candidates: string[];
  };
  validation_badges: Array<{ status: string; label: string }>;
};

export type UploadResponse = {
  upload_id: string;
  filename: string;
  profile_url: string;
};

export type CsvPreview = {
  upload_id: string;
  filename: string;
  columns: string[];
  rows: Array<Record<string, unknown>>;
  limit: number;
};

export type WorkflowDraft = {
  workflow_id: string;
  upload_id?: string | null;
  name: string;
  dataset: Record<string, unknown>;
  column_mapping: Record<string, unknown>;
  outcome: Record<string, unknown>;
  prior_grid: Record<string, unknown>;
  structural: Record<string, unknown>;
  sampler: Record<string, unknown>;
  status: string;
};

export type WorkflowDraftRequest = Partial<Omit<WorkflowDraft, "workflow_id" | "status">>;

export type ConfigPreview = {
  workflow_id: string;
  yaml: string;
  estimated_run_count: number;
  warnings: string[];
  errors: string[];
  normalized_config: Record<string, unknown>;
};

export type ResultPayloadResponse<TPayload = unknown> = {
  run_id: string;
  payload: TPayload;
};

export type RunLifecycleStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

export type RunProgress = {
  total_runs: number;
  completed_runs: number;
  failed_runs: number;
  active_target_channel: string | null;
  active_mu: number | null;
  active_sigma: number | null;
  active_dist: string | null;
};

export type ChannelRunProgress = {
  channel: string;
  total_runs: number;
  completedRuns: number;
  failedRuns: number;
  status: RunLifecycleStatus;
};

export type RunStatus = {
  run_id: string;
  workflow_id: string;
  status: RunLifecycleStatus;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  progress: RunProgress;
  channel_progress: ChannelRunProgress[];
  messages: string[];
  monitor_url: string;
  result_url: string | null;
  mode: string;
  work_dir?: string | null;
  config_path?: string | null;
  log_path?: string | null;
  process_id?: number | null;
  output_tag?: string | null;
  result_artifacts?: Record<string, unknown>;
};

export type RunCreateRequest = {
  workflow_id: string;
  approved_config_preview: ConfigPreview;
  mode?: "mock" | "real_tiny" | "real_full";
};

export type RunLogsResponse = {
  run_id: string;
  lines: string[];
};
