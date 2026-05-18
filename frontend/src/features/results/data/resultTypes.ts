export type DashboardPayload = {
  meta?: {
    title?: string;
    subtitle?: string;
    generated_at?: string;
  };
  overview?: {
    n_rows?: number;
    n_channels?: number;
    n_dists?: number;
    n_target_sets?: number;
    ranking_rows_total?: number;
    ranking_rows_used?: number;
    overview_self_response_rows?: number;
  };
  outcome_context?: {
    metric_label?: string;
    kpi_type?: string;
    kpi_type_effective?: string;
    revenue_per_kpi?: number;
  };
  diagnostics_overview?: {
    n_runs?: number;
    pass_runs?: number;
    review_runs?: number;
    fail_runs?: number;
    unknown_runs?: number;
    pass_rate_pct?: number;
    review_rate_pct?: number;
    fail_rate_pct?: number;
  };
  diagnostics?: {
    available?: boolean;
    overview?: DashboardPayload["diagnostics_overview"];
    status_rows?: Array<Record<string, unknown>>;
    primary_rows?: Array<Record<string, unknown>>;
    flagged_rows?: Array<Record<string, unknown>>;
    check_rows?: Array<DiagnosticCheckRow>;
    reason?: string;
  };
  decision_card?: {
    available?: boolean;
    tier?: string;
    tier_class?: string;
    headline?: string;
    score_value?: string;
    score_numeric?: number;
    score_band?: string;
    reasons?: string[];
    actions?: string[];
    triggered_rules?: string[];
    policy_rules?: string[];
    score_note?: string;
    score_label?: string;
    score_meta?: Record<string, unknown>;
  };
  rank_rows?: RankRow[];
  roi_tornado_rows?: RoiTornadoRow[];
  dollar_tornado_rows?: DollarTornadoRow[];
  target_channel_detail?: TargetChannelDetail;
  quick_overview_lines?: string[];
  recommendations?: string[];
  roi_prior_posterior_table?: PosteriorEvidenceTable;
  scenario_items?: ScenarioItem[];
  structural?: StructuralSection;
  workbench?: WorkbenchSection;
  how_this_was_run?: AuditSection;
  qc_followup?: {
    available?: boolean;
    primary_review_check?: string;
    count?: number;
    reason?: string;
  };
};

export type DiagnosticCheckRow = {
  check?: string;
  pass_count?: number | string;
  review_count?: number | string;
  fail_count?: number | string;
  unknown_count?: number | string;
  coverage_pct?: number | string;
  recommendation?: string;
};

export type RankRow = {
  channel?: string;
  roi_prior_dist?: string;
  baseline_roi?: number;
  max_abs_pct_change?: number;
  max_abs_delta_roi?: number;
  primary_metric?: string;
  primary_value?: number;
  pct_metric_reliable?: boolean;
};

export type RoiTornadoRow = {
  channel?: string;
  left?: number;
  right?: number;
  impact?: number;
  n?: number;
  source?: string;
  unit?: string;
};

export type DollarTornadoRow = {
  channel?: string;
  left_dollar?: number;
  right_dollar?: number;
  max_abs_dollar_change?: number;
  median_dollar_change?: number;
  n?: number;
};

export type TargetChannelDetail = {
  available?: boolean;
  default_channel?: string;
  recommended_channel?: string;
  recommendation_source?: string;
  options?: Array<{ value?: string; label?: string }>;
  summaries?: Record<string, unknown>;
};

export type PosteriorEvidenceTable = {
  available?: boolean;
  rows?: Array<Record<string, unknown>>;
  reason?: string;
};

export type ScenarioItem = Record<string, unknown>;

export type StructuralSection = {
  available?: boolean;
  selected_run_id?: string;
  selected_profile_id?: string;
  notes?: string[];
  profile_rows?: Array<Record<string, unknown>>;
  run_rows?: Array<Record<string, unknown>>;
  response_rows?: Array<Record<string, unknown>>;
  carryover_rows?: Array<Record<string, unknown>>;
  adstock_curve_rows?: Array<Record<string, unknown>>;
  saturation_curve_rows?: Array<Record<string, unknown>>;
};

export type WorkbenchSection = {
  available?: boolean;
  notes?: string;
  explicit_baseline?: Record<string, unknown>;
  dist_config?: Record<string, unknown>;
  contribution_col?: string;
  contribution_delta_col?: string;
  default_channel?: string;
  available_channels?: string[];
  mu_values?: number[];
  sigma_values?: number[];
  run_rows?: Array<Record<string, unknown>>;
  channel_summary_rows?: Array<Record<string, unknown>>;
  mu_marginal_rows?: Array<Record<string, unknown>>;
  sigma_marginal_rows?: Array<Record<string, unknown>>;
};

export type AuditSection = {
  available?: boolean;
  summary?: string;
  badges?: Array<{ label?: string; value?: string }>;
  flow_cards?: Array<{ step?: string; title?: string; detail?: string }>;
  workflow_steps?: string[];
  settings?: Array<{ label?: string; value?: string }>;
};
