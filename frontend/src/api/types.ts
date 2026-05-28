export type HealthResponse = {
  status: string;
  service: string;
};

export type ColumnProfile = {
  name: string;
  inferred_type: "date" | "number" | "string" | "boolean" | "unknown";
  null_rate: number;
  nonzero_rate?: number | null;
  total_value?: number | null;
  status?: "valid" | "warning" | "missing";
  sample_values: unknown[];
};

export type DateProfile = {
  column: string | null;
  date_min: string | null;
  date_max: string | null;
  valid_parse_rate: number;
  inferred_frequency: string | null;
  status: "valid" | "warning" | "missing";
  message: string;
};

export type ChannelDiagnostic = {
  channel: string;
  spend_column: string | null;
  media_column: string | null;
  spend_null_rate: number | null;
  spend_nonzero_rate: number | null;
  spend_total: number | null;
  media_null_rate: number | null;
  media_nonzero_rate: number | null;
  media_total: number | null;
  status: "active_paid_media" | "spend_as_media_fallback" | "inactive_all_zero" | "not_eligible_paid_media";
  severity: "valid" | "warning" | "missing";
  include_in_model: boolean;
  message: string;
};

export type ReadinessCheck = {
  code: string;
  label: string;
  status: "valid" | "warning" | "error" | "info";
  message: string;
};

export type ReadinessSummary = {
  status: "valid" | "warning" | "error" | "info";
  checks: ReadinessCheck[];
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
    revenue_per_kpi_candidates: string[];
    control_candidates: string[];
    geo_candidates: string[];
    population_candidates: string[];
  };
  date_profile?: DateProfile;
  channel_diagnostics?: ChannelDiagnostic[];
  schema_readiness?: ReadinessSummary;
  modeling_readiness?: ReadinessSummary;
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
  output_tag?: string | null;
  source?: string;
  payload: TPayload;
};

export type ResultHistoryItem = {
  history_id: string;
  run_id: string;
  output_tag: string;
  display_result_id?: string | null;
  config_fingerprint?: string | null;
  original_csv_filename?: string | null;
  csv_name_prefix?: string | null;
  dataset_hash?: string | null;
  generated_at?: string | null;
  completed_at?: string | null;
  kpi?: string | null;
  kpi_path?: string | null;
  revenue_handling?: string | null;
  channels: string[];
  channel_count: number;
  completed_runs?: number | null;
  qc_pass_runs?: number | null;
  qc_review_runs?: number | null;
  qc_fail_runs?: number | null;
  qc_mix?: Record<string, number>;
  report_path?: string | null;
  dashboard_path?: string | null;
  payload_path: string;
  react_result_url?: string | null;
  static_report_path?: string | null;
};

export type ResultHistoryResponse = {
  items: ResultHistoryItem[];
};

export type ResultHistoryPayloadResponse<TPayload = unknown> = ResultPayloadResponse<TPayload> & {
  history_id: string;
  history_item: ResultHistoryItem;
};

export type RunLifecycleStatus = "queued" | "running" | "completed" | "failed" | "cancelled" | "already_completed";

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
  display_result_id?: string | null;
  config_fingerprint?: string | null;
  original_csv_filename?: string | null;
  csv_name_prefix?: string | null;
  dataset_hash?: string | null;
  history_id?: string | null;
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
