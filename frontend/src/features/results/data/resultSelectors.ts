import type { DashboardPayload, DollarTornadoRow, RankRow, RoiTornadoRow } from "./resultTypes";

const emptyArray: never[] = [];

export function formatNumber(value: unknown, digits = 0): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return "Unavailable";
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(n);
}

export function formatPercent(value: unknown, digits = 1): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return "Unavailable";
  return `${formatNumber(n, digits)}%`;
}

export function formatMoneyCompact(value: unknown): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return "Unavailable";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(n);
}

export function channelLabel(channel: unknown): string {
  return String(channel || "Unavailable").toUpperCase();
}

export function selectResultHeader(payload: DashboardPayload) {
  return {
    title: payload.meta?.title || "Prior Sensitivity Dashboard",
    subtitle: payload.meta?.subtitle || "Generated Meridian prior-sensitivity output",
    generatedAt: payload.meta?.generated_at || "Unavailable",
  };
}

export function selectOverviewStats(payload: DashboardPayload) {
  const diagnostics = payload.diagnostics_overview || {};
  const overview = payload.overview || {};
  const outcome = payload.outcome_context || {};

  return {
    completedRuns: diagnostics.n_runs ?? overview.n_rows ?? 0,
    modeledChannels: overview.n_channels ?? payload.target_channel_detail?.options?.length ?? 0,
    metricLabel: outcome.metric_label || "ROI",
    kpiType: outcome.kpi_type || "Unavailable",
    effectiveKpiType: outcome.kpi_type_effective || "Unavailable",
    revenuePerKpi: outcome.revenue_per_kpi,
    passRatePct: diagnostics.pass_rate_pct,
    passRuns: diagnostics.pass_runs ?? 0,
    reviewRuns: diagnostics.review_runs ?? 0,
    failRuns: diagnostics.fail_runs ?? 0,
    unknownRuns: diagnostics.unknown_runs ?? 0,
    selfResponseRows: overview.overview_self_response_rows ?? overview.ranking_rows_total ?? 0,
  };
}

export function selectLargestSelfResponse(payload: DashboardPayload): RankRow | undefined {
  return [...(payload.rank_rows || emptyArray)].sort((a, b) => {
    return Number(b.primary_value ?? b.max_abs_pct_change ?? 0) - Number(a.primary_value ?? a.max_abs_pct_change ?? 0);
  })[0];
}

export function selectSelfResponseTornadoRows(payload: DashboardPayload): RoiTornadoRow[] {
  return [...(payload.roi_tornado_rows || emptyArray)].sort((a, b) => {
    return Number(b.impact ?? 0) - Number(a.impact ?? 0);
  });
}

export function selectDollarTornadoRows(payload: DashboardPayload): DollarTornadoRow[] {
  return [...(payload.dollar_tornado_rows || emptyArray)].sort((a, b) => {
    return Number(b.max_abs_dollar_change ?? 0) - Number(a.max_abs_dollar_change ?? 0);
  });
}

export function selectDiagnosticContext(payload: DashboardPayload) {
  const decision = payload.decision_card;
  const qc = payload.qc_followup;
  const diagnostics = payload.diagnostics_overview || {};

  return {
    tier: decision?.tier || "Unavailable",
    headline: decision?.headline || "Diagnostic summary unavailable.",
    scoreValue: decision?.score_value || "Unavailable",
    reasons: decision?.reasons || [],
    interpretationNotes: [...(decision?.reasons || []), ...(payload.quick_overview_lines || [])],
    cautionFlags: [...(decision?.actions || []), ...(payload.recommendations || [])],
    primaryReviewCheck: qc?.primary_review_check || "Unavailable",
    reviewCount: qc?.count ?? diagnostics.review_runs ?? 0,
  };
}

export function selectResultSectionCounts(payload: DashboardPayload) {
  return {
    priorSensitivityRows: payload.rank_rows?.length ?? 0,
    posteriorEvidenceRows: payload.roi_prior_posterior_table?.rows?.length ?? 0,
    scenarioItems: payload.scenario_items?.length ?? payload.workbench?.run_rows?.length ?? 0,
    structuralProfiles: payload.structural?.profile_rows?.length ?? 0,
    structuralRuns: payload.structural?.run_rows?.length ?? 0,
    auditBadges: payload.how_this_was_run?.badges?.length ?? 0,
  };
}

export function selectChannelSummaryRows(payload: DashboardPayload) {
  return [...(payload.workbench?.channel_summary_rows || emptyArray)].sort((a, b) => {
    return Number(b.pct_change_abs_max ?? 0) - Number(a.pct_change_abs_max ?? 0);
  });
}

export function selectScenarioSnapshots(payload: DashboardPayload) {
  return [...(payload.scenario_items || emptyArray)];
}

export function selectStructuralProfileRows(payload: DashboardPayload) {
  return [...(payload.structural?.profile_rows || emptyArray)];
}

export function selectStructuralRunRows(payload: DashboardPayload) {
  return [...(payload.structural?.run_rows || emptyArray)];
}
