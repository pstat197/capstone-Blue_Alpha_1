import type { DashboardPayload, DollarTornadoRow, RankRow, RoiTornadoRow } from "./resultTypes";

const emptyArray: never[] = [];

export function formatNumber(value: unknown, digits = 0): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return "NA";
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(n);
}

export function formatPercent(value: unknown, digits = 1): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return "NA";
  return `${formatNumber(n, digits)}%`;
}

export function formatMoneyCompact(value: unknown): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return "NA";
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

export function formatMovementValue(row: RankRow | undefined): string {
  const metric = String(row?.primary_metric || "").toLowerCase();
  const value = row?.primary_value ?? row?.max_abs_pct_change ?? row?.max_abs_delta_roi;
  if (metric.includes("delta")) return formatNumber(value, 3);
  return formatPercent(value, 2);
}

export function selectResultHeader(payload: DashboardPayload) {
  return {
    title: payload.meta?.title || "Prior Sensitivity Dashboard",
    subtitle: payload.meta?.subtitle || "Generated Meridian prior-sensitivity output",
    generatedAt: payload.meta?.generated_at || "Not available",
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
    kpiType: outcome.kpi_type || "Not available",
    effectiveKpiType: outcome.kpi_type_effective || "Not available",
    revenuePerKpi: outcome.revenue_per_kpi,
    passRatePct: diagnostics.pass_rate_pct,
    passRuns: diagnostics.pass_runs ?? 0,
    reviewRuns: diagnostics.review_runs ?? 0,
    failRuns: diagnostics.fail_runs ?? 0,
    unknownRuns: diagnostics.unknown_runs ?? 0,
    selfResponseRows: overview.overview_self_response_rows ?? overview.ranking_rows_total ?? 0,
  };
}

export function selectRunScope(payload: DashboardPayload) {
  const settings = payload.how_this_was_run?.settings || [];
  const badges = payload.how_this_was_run?.badges || [];
  const settingValue = (label: string) => settings.find((item) => item.label?.toLowerCase() === label.toLowerCase())?.value;
  const badgeValue = (label: string) => badges.find((item) => item.label?.toLowerCase() === label.toLowerCase())?.value;
  const runMode = settingValue("Run mode") || badgeValue("Run Mode");
  const gridScope = settingValue("Prior grid scope") || badgeValue("Sweep Scope");
  const gridDefinition = settingValue("Grid definition") || badgeValue("Grid");
  const isFixedGrid = String(gridScope || gridDefinition || "").toLowerCase().includes("grid");

  return {
    value: isFixedGrid ? "Fixed-grid prior sensitivity audit" : runMode || gridScope || "Prior sensitivity audit",
    note: gridDefinition || payload.how_this_was_run?.summary || "Generated audit scope",
  };
}

export function selectLargestSelfResponse(payload: DashboardPayload): RankRow | undefined {
  return [...(payload.rank_rows || emptyArray)].sort((a, b) => {
    return Number(b.primary_value ?? b.max_abs_pct_change ?? 0) - Number(a.primary_value ?? a.max_abs_pct_change ?? 0);
  })[0];
}

export function selectSelfResponseTornadoRows(payload: DashboardPayload): RoiTornadoRow[] {
  const summaries = payload.target_channel_detail?.summaries || {};
  const summaryRows = Object.entries(summaries)
    .map(([target, summary]) => {
      const impact = (summary.system_impact_rows || []).find((row) => {
        const channel = String(row.channel || "").toLowerCase();
        return Boolean(row.is_self_response) || channel === target.toLowerCase();
      });
      if (!impact) return null;
      const left = Number(impact.left_pct ?? 0);
      const right = Number(impact.right_pct ?? 0);
      const impactValue = Number(impact.max_abs_delta_pct ?? Math.max(Math.abs(left), Math.abs(right)));
      if (!Number.isFinite(impactValue)) return null;
      return {
        channel: target,
        left: Number.isFinite(left) ? left : 0,
        right: Number.isFinite(right) ? right : 0,
        impact: impactValue,
        n: impact.n_rows,
        source: "target_channel_detail.self_response",
        unit: "pct",
      };
    })
    .filter((row): row is NonNullable<typeof row> => row !== null);
  if (summaryRows.length) {
    return summaryRows.sort((a, b) => Math.abs(Number(b.impact ?? 0)) - Math.abs(Number(a.impact ?? 0)));
  }

  return [...(payload.roi_tornado_rows || emptyArray)].sort((a, b) => {
    return Math.abs(Number(b.impact ?? 0)) - Math.abs(Number(a.impact ?? 0));
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
    tier: decision?.tier || "Not available",
    headline: decision?.headline || "Diagnostic summary unavailable.",
    scoreValue: decision?.score_value || "Not available",
    reasons: decision?.reasons || [],
    interpretationNotes: [...(decision?.reasons || []), ...(payload.quick_overview_lines || [])],
    cautionFlags: [...(decision?.actions || []), ...(payload.recommendations || [])],
    primaryReviewCheck: qc?.primary_review_check || "Not available",
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
