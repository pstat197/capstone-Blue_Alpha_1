import { useState, type ReactNode } from "react";

import { SectionScaffold } from "../components/SectionScaffold";
import { ContextualHelpButton } from "../../../shared/ContextualHelp";
import { useCurrentResult } from "../data/resultLoader";
import { formatNumber } from "../data/resultSelectors";

type PosteriorPoint = {
  channel: string;
  variant: string;
  variantShort: string;
  priorMean: number | null;
  sigma: number | null;
  mean: number;
  lower50: number;
  upper50: number;
};

type ChannelUpdate = {
  channel: string;
  avgPosterior: number | null;
  baselinePosterior: number | null;
  roiMin: number | null;
  roiMax: number | null;
  ciWidth: number | null;
  sensitivity: number | null;
  avgAbsShift: number | null;
  maxShift: number | null;
  strength: "Strong" | "Moderate" | "Weak" | "Unavailable";
  stability: "Stable" | "Watch" | "Prior-sensitive" | "High uncertainty" | "Unavailable";
};

type SensitivityRisk = "High" | "Medium" | "Low" | "Unavailable";

type ConfidenceSummary = {
  level: "Low" | "Medium" | "High";
  pass: number;
  review: number;
  fail: number;
  completed: number;
  reason: string;
  guidance: string;
};

const variantColors = ["#2f80ed", "#43c59e", "#ff9f1c", "#6f52c7", "#f24472", "#c26d5f", "#e05ac5", "#29a4b5", "#7a8a9d", "#1b9aaa"];

function toNumber(value: unknown): number | null {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function titleCase(value: string): string {
  return value.replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatMaybe(value: unknown, digits = 2): string {
  const n = toNumber(value);
  return n === null ? "NA" : formatNumber(n, digits);
}

function formatRange(min: number | null, max: number | null): string {
  return min === null || max === null ? "NA" : `${formatNumber(min, 2)} - ${formatNumber(max, 2)}`;
}

function stabilityClass(stability: ChannelUpdate["stability"]): string {
  return stability.toLowerCase().replace(/\s+/g, "-");
}

function channelsText(rows: ChannelUpdate[]): string {
  return rows.length ? rows.map((row) => titleCase(row.channel)).join(", ") : "Unavailable";
}

function median(values: Array<number | null | undefined>): number | null {
  const nums = values.filter((value): value is number => Number.isFinite(value)).sort((a, b) => a - b);
  if (!nums.length) return null;
  const mid = Math.floor(nums.length / 2);
  return nums.length % 2 ? nums[mid] : (nums[mid - 1] + nums[mid]) / 2;
}

function percentile(values: Array<number | null | undefined>, p: number): number | null {
  const nums = values.filter((value): value is number => Number.isFinite(value)).sort((a, b) => a - b);
  if (!nums.length) return null;
  const idx = (nums.length - 1) * p;
  const lower = Math.floor(idx);
  const upper = Math.ceil(idx);
  if (lower === upper) return nums[lower];
  return nums[lower] + (nums[upper] - nums[lower]) * (idx - lower);
}

function variantLabel(row: Record<string, unknown>) {
  const explicit = String(row.prior_variant || "").trim();
  if (explicit) {
    return explicit.replace(/, dist=[^,]+/i, "");
  }
  const mu = toNumber(row.prior_roi_mu);
  const sigma = toNumber(row.prior_roi_sigma);
  if (mu !== null || sigma !== null) return `mu=${mu ?? "NA"}, sigma=${sigma ?? "NA"}`;
  return "Prior variant unavailable";
}

function parsePosteriorRows(rows: Array<Record<string, unknown>> | undefined): PosteriorPoint[] {
  return (rows || [])
    .map((row) => {
      const channel = String(row.channel || "").trim();
      const mean = toNumber(row.posterior_roi_estimate);
      const lower50 = toNumber(row.posterior_50_lower);
      const upper50 = toNumber(row.posterior_50_upper);
      if (!channel || mean === null || lower50 === null || upper50 === null) return null;
      const variant = variantLabel(row);
      return {
        channel,
        variant,
        variantShort: variant,
        priorMean: toNumber(row.prior_roi_mu),
        sigma: toNumber(row.prior_roi_sigma),
        mean,
        lower50,
        upper50,
      };
    })
    .filter((row): row is PosteriorPoint => Boolean(row));
}

function nearestBaseline(points: PosteriorPoint[]): PosteriorPoint | null {
  const withPrior = points.filter((point) => point.priorMean !== null || point.sigma !== null);
  const candidates = withPrior.length ? withPrior : points;
  return [...candidates].sort((a, b) => {
    const aScore = Math.abs((a.priorMean ?? 1) - 1) + Math.abs((a.sigma ?? 1) - 1);
    const bScore = Math.abs((b.priorMean ?? 1) - 1) + Math.abs((b.sigma ?? 1) - 1);
    return aScore - bScore;
  })[0] || null;
}

function classifyChannels(points: PosteriorPoint[]): ChannelUpdate[] {
  const byChannel = new Map<string, PosteriorPoint[]>();
  points.forEach((point) => byChannel.set(point.channel, [...(byChannel.get(point.channel) || []), point]));

  const baseRows = [...byChannel.entries()].map(([channel, channelPoints]) => {
    const baseline = nearestBaseline(channelPoints);
    const means = channelPoints.map((point) => point.mean);
    const avgAbsShift = baseline ? means.reduce((sum, mean) => sum + Math.abs(mean - baseline.mean), 0) / means.length : null;
    const maxShift = baseline ? Math.max(...means.map((mean) => Math.abs(mean - baseline.mean))) : null;
    const sortedMeans = [...means].sort((a, b) => a - b);
    const q1 = percentile(sortedMeans, 0.25);
    const q3 = percentile(sortedMeans, 0.75);
    return {
      channel,
      avgPosterior: means.reduce((sum, value) => sum + value, 0) / means.length,
      baselinePosterior: baseline?.mean ?? null,
      roiMin: means.length ? Math.min(...means) : null,
      roiMax: means.length ? Math.max(...means) : null,
      ciWidth: channelPoints.reduce((sum, point) => sum + (point.upper50 - point.lower50), 0) / channelPoints.length,
      sensitivity: q1 !== null && q3 !== null ? q3 - q1 : null,
      avgAbsShift,
      maxShift,
      strength: "Unavailable" as ChannelUpdate["strength"],
      stability: "Unavailable" as ChannelUpdate["stability"],
    };
  });

  const weakCut = percentile(baseRows.map((row) => row.avgAbsShift), 0.33);
  const strongCut = percentile(baseRows.map((row) => row.avgAbsShift), 0.67);
  const watchShiftCut = percentile(baseRows.map((row) => row.maxShift), 0.5);
  const priorSensitiveCut = percentile(baseRows.map((row) => row.maxShift), 0.75);
  const highUncertaintyCut = percentile(baseRows.map((row) => row.ciWidth), 0.75);

  return baseRows
    .map((row) => {
      // When no formal update classification is present in the payload, strength is derived
      // from within-run posterior movement: top third of avg absolute shift = Strong,
      // middle third = Moderate, bottom third = Weak. No channel names or values are hardcoded.
      const strength: ChannelUpdate["strength"] =
        row.avgAbsShift === null || weakCut === null || strongCut === null
          ? "Unavailable"
          : row.avgAbsShift >= strongCut
            ? "Strong"
            : row.avgAbsShift >= weakCut
              ? "Moderate"
              : "Weak";
      // Stability summarizes whether the posterior conclusion remains similar as priors vary.
      // It is derived from existing posterior means and 50% interval widths within the selected run:
      // top-quartile max shift = Prior-sensitive, top-quartile CI width = High uncertainty,
      // above-median max shift = Watch, otherwise Stable.
      const stability: ChannelUpdate["stability"] =
        row.maxShift === null || row.ciWidth === null || watchShiftCut === null || priorSensitiveCut === null || highUncertaintyCut === null
          ? "Unavailable"
          : row.maxShift >= priorSensitiveCut
            ? "Prior-sensitive"
            : row.ciWidth >= highUncertaintyCut
              ? "High uncertainty"
              : row.maxShift >= watchShiftCut
                ? "Watch"
                : "Stable";
      return { ...row, strength, stability };
    })
    .sort((a, b) => Number(b.avgAbsShift ?? -1) - Number(a.avgAbsShift ?? -1));
}

function confidenceFromPayload(payload: ReturnType<typeof useCurrentResult>["payload"]) {
  const diagnostics = payload.diagnostics_overview;
  const decisionTier = String(payload.decision_card?.tier || "").toLowerCase();
  const passRate = toNumber(diagnostics?.pass_rate_pct);
  if (decisionTier.includes("low") || String(payload.qc_followup?.primary_review_check || "").trim()) return "Low";
  if (decisionTier.includes("high") || (passRate !== null && passRate >= 80)) return "High";
  if (passRate !== null && passRate >= 50) return "Medium";
  return diagnostics ? "Low" : "Medium";
}

function interpretationConfidence(payload: ReturnType<typeof useCurrentResult>["payload"]): ConfidenceSummary {
  const diagnostics = payload.diagnostics_overview || payload.diagnostics?.overview || {};
  const pass = toNumber(diagnostics.pass_runs) ?? 0;
  const review = toNumber(diagnostics.review_runs) ?? 0;
  const fail = toNumber(diagnostics.fail_runs) ?? 0;
  const unknown = toNumber(diagnostics.unknown_runs) ?? 0;
  const completed = toNumber(diagnostics.n_runs) ?? pass + review + fail + unknown;
  const passRate = toNumber(diagnostics.pass_rate_pct);
  const primaryReviewCheck = String(payload.qc_followup?.primary_review_check || "").trim();
  const reviewCount = toNumber(payload.qc_followup?.count) ?? review;
  const level = confidenceFromPayload(payload);

  let reason = "Diagnostic confidence details are unavailable in this payload.";
  if (completed || pass || review || fail || primaryReviewCheck) {
    const passRateText = passRate === null ? "QC pass rate is unavailable" : `${formatNumber(passRate, 0)}% QC pass rate`;
    const allReviewText = completed && review === completed ? `All ${formatNumber(completed, 0)} completed run${completed === 1 ? " is" : "s are"} REVIEW` : `PASS ${formatNumber(pass, 0)} / REVIEW ${formatNumber(review, 0)} / FAIL ${formatNumber(fail, 0)}`;
    const primaryText = primaryReviewCheck ? `, driven by ${primaryReviewCheck}${reviewCount && reviewCount !== review ? ` across ${formatNumber(reviewCount, 0)} review run${reviewCount === 1 ? "" : "s"}` : ""}` : "";
    reason = `${passRateText}. ${allReviewText}${primaryText}.`;
  }

  const guidance =
    level === "High"
      ? "Use these results for planning decisions while continuing normal diagnostic review."
      : level === "Medium"
        ? "Use these results directionally and review sensitivity or QC issues before major budget changes."
        : "Use these results directionally only. Resolve QC/stability issues before making budget-level decisions.";

  return { level, pass, review, fail, completed, reason, guidance };
}

function sensitivityRiskGroups(rows: ChannelUpdate[]) {
  const mediumCut = percentile(rows.map((row) => row.sensitivity), 0.33);
  const highCut = percentile(rows.map((row) => row.sensitivity), 0.67);
  const grouped: Record<SensitivityRisk, ChannelUpdate[]> = {
    High: [],
    Medium: [],
    Low: [],
    Unavailable: [],
  };

  rows.forEach((row) => {
    if (row.sensitivity === null || mediumCut === null || highCut === null) {
      grouped.Unavailable.push(row);
    } else if (row.sensitivity >= highCut) {
      grouped.High.push(row);
    } else if (row.sensitivity >= mediumCut) {
      grouped.Medium.push(row);
    } else {
      grouped.Low.push(row);
    }
  });

  return grouped;
}

function EmptyState({ message }: { message: string }) {
  return <div className="pvp-empty-state">{message}</div>;
}

function InfoPopover({ label, children }: { label: string; children: ReactNode }) {
  return (
    <details className="pvp-info-popover">
      <summary aria-label={label}>i</summary>
      <div className="pvp-info-popover-panel" role="note">
        {children}
      </div>
    </details>
  );
}

function SummaryCard({
  title,
  value,
  subtitle,
}: {
  title: string;
  value: string;
  subtitle: string;
}) {
  return (
    <article className="pvp-summary-card">
      <div>
        <h3>{title}</h3>
        <strong>{value}</strong>
        <p>{subtitle}</p>
      </div>
    </article>
  );
}

function ConfidenceCard({ confidence }: { confidence: ConfidenceSummary }) {
  return (
    <article className="content-panel pvp-confidence-card">
      <div className="pvp-card-title pvp-card-title--compact">
        <div className="inline-help-row">
          <h3>Interpretation Confidence</h3>
          <ContextualHelpButton sectionId="interpretation-confidence" label="Explain interpretation confidence" />
        </div>
        <span className={`pvp-confidence-badge pvp-confidence-badge--${confidence.level.toLowerCase()}`}>{confidence.level}</span>
      </div>
      <div className="pvp-confidence-chips" aria-label="QC status summary">
        <span className="pvp-confidence-chip pvp-confidence-chip--pass">PASS {formatNumber(confidence.pass, 0)}</span>
        <span className="pvp-confidence-chip pvp-confidence-chip--review">REVIEW {formatNumber(confidence.review, 0)}</span>
        <span className="pvp-confidence-chip pvp-confidence-chip--fail">FAIL {formatNumber(confidence.fail, 0)}</span>
        <span>{formatNumber(confidence.completed, 0)} completed runs</span>
      </div>
      <div className="pvp-confidence-copy">
        <div>
          <h4>Why confidence is {confidence.level.toLowerCase()}</h4>
          <p>{confidence.reason}</p>
        </div>
        <div>
          <h4>How to use this</h4>
          <p>{confidence.guidance}</p>
        </div>
      </div>
    </article>
  );
}

function PriorPosteriorChart({ points, metricLabel }: { points: PosteriorPoint[]; metricLabel: string }) {
  const [highlightedVariant, setHighlightedVariant] = useState<string | null>(null);

  if (!points.length) return <EmptyState message="Prior-vs-posterior rows are unavailable for this run." />;

  const channels = [...new Set(points.map((point) => point.channel))];
  const variants = [...new Set(points.map((point) => point.variantShort))];
  const values = points.flatMap((point) => [point.lower50, point.upper50, point.mean, point.priorMean ?? 1]);
  const minValue = Math.min(0, ...values);
  const maxValue = Math.max(1, ...values);
  const span = maxValue - minValue || 1;
  const width = 1060;
  const rowHeight = 54;
  const top = 26;
  const left = 112;
  const right = 34;
  const bottom = 50;
  const plotWidth = width - left - right;
  const height = top + channels.length * rowHeight + bottom;
  const x = (value: number) => left + ((value - minValue) / span) * plotWidth;
  const ticks = Array.from({ length: 6 }, (_, idx) => minValue + (span * idx) / 5);
  const baselineX = x(1);

  return (
    <div className="pvp-chart-shell">
      <div className="pvp-plot-scroll">
        <svg className="pvp-main-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="ROI prior vs posterior chart">
          {ticks.map((tick) => (
            <g key={tick}>
              <line x1={x(tick)} x2={x(tick)} y1={top - 8} y2={height - bottom} className="pvp-chart-grid" />
              <text x={x(tick)} y={height - 18} textAnchor="middle" className="pvp-chart-tick">
                {formatMaybe(tick, 1)}
              </text>
            </g>
          ))}
          {baselineX >= left && baselineX <= width - right ? <line x1={baselineX} x2={baselineX} y1={top - 10} y2={height - bottom} className="pvp-chart-baseline" /> : null}
          {channels.map((channel, channelIndex) => {
            const yBase = top + channelIndex * rowHeight + rowHeight / 2;
            const channelPoints = points.filter((point) => point.channel === channel);
            return (
              <g key={channel}>
                <text x={left - 14} y={yBase + 4} textAnchor="end" className="pvp-chart-channel">
                  {channel}
                </text>
                <line x1={left} x2={width - right} y1={yBase} y2={yBase} className="pvp-chart-row" />
                {channelPoints.map((point, variantIndex) => {
                  const offset = ((variantIndex % variants.length) - (variants.length - 1) / 2) * Math.min(4, 22 / Math.max(variants.length, 1));
                  const color = variantColors[variants.indexOf(point.variantShort) % variantColors.length];
                  const y = yBase + offset;
                  const isDimmed = highlightedVariant !== null && highlightedVariant !== point.variantShort;
                  const opacity = isDimmed ? 0.2 : 1;
                  return (
                    <g
                      key={`${channel}-${point.variantShort}`}
                      opacity={opacity}
                      onMouseEnter={() => setHighlightedVariant(point.variantShort)}
                      onMouseLeave={() => setHighlightedVariant(null)}
                    >
                      <line x1={x(point.lower50)} x2={x(point.upper50)} y1={y} y2={y} stroke={color} strokeWidth={isDimmed ? "2.2" : "3"} opacity="0.86" />
                      <line x1={x(point.lower50)} x2={x(point.lower50)} y1={y - 3.6} y2={y + 3.6} stroke={color} strokeWidth="1.8" opacity="0.76" />
                      <line x1={x(point.upper50)} x2={x(point.upper50)} y1={y - 3.6} y2={y + 3.6} stroke={color} strokeWidth="1.8" opacity="0.76" />
                      {point.priorMean !== null ? (
                        <rect
                          x={x(point.priorMean) - 5.4}
                          y={y - 5.4}
                          width="10.8"
                          height="10.8"
                          className="pvp-prior-mean-marker"
                          transform={`rotate(45 ${x(point.priorMean)} ${y})`}
                        />
                      ) : null}
                      <circle cx={x(point.mean)} cy={y} r={isDimmed ? "4.4" : "5.1"} fill={color} stroke="#ffffff" strokeWidth="1.5" />
                    </g>
                  );
                })}
              </g>
            );
          })}
          <text x={left + plotWidth / 2} y={height - 2} textAnchor="middle" className="pvp-chart-axis">
            {metricLabel}
          </text>
        </svg>
      </div>
      <div className="pvp-legend-card">
        <div className="pvp-marker-legend" aria-label="Chart marker legend">
          <span><i className="pvp-marker-dot" /> Dots = posterior mean</span>
          <span><i className="pvp-marker-line" /> Lines = 50% posterior interval</span>
          <span><i className="pvp-marker-diamond" /> Diamonds = channel prior mean</span>
          <span><i className="pvp-marker-dash" /> Dashed line = ROI 1.0 reference</span>
        </div>
        <details className="pvp-variant-accordion">
          <summary>Prior variants</summary>
          <div className="pvp-legend-list">
            {variants.map((variant, index) => (
              <button
                className={`pvp-legend-item${highlightedVariant === variant ? " pvp-legend-item--active" : ""}`}
                key={variant}
                type="button"
                onMouseEnter={() => setHighlightedVariant(variant)}
                onMouseLeave={() => setHighlightedVariant(null)}
                onFocus={() => setHighlightedVariant(variant)}
                onBlur={() => setHighlightedVariant(null)}
              >
                <span style={{ background: variantColors[index % variantColors.length] }} />
                <b>{variant}</b>
              </button>
            ))}
          </div>
        </details>
      </div>
    </div>
  );
}

function ShiftChart({ rows }: { rows: ChannelUpdate[] }) {
  const validRows = rows.filter((row) => row.avgAbsShift !== null);
  if (!validRows.length) return <EmptyState message="Baseline prior rows are unavailable, so channel shift cannot be calculated." />;
  const maxShift = Math.max(...validRows.map((row) => row.avgAbsShift || 0)) || 1;
  const density = validRows.length <= 5 ? "compact" : validRows.length >= 9 ? "dense" : "normal";
  return (
    <div className={`pvp-shift-bars pvp-shift-bars--${density}`}>
      {validRows.map((row) => {
        const value = row.avgAbsShift || 0;
        return (
          <div className="pvp-shift-row" key={row.channel}>
            <span>{row.channel}</span>
            <div className="pvp-shift-track">
              <div style={{ width: `${Math.max(3, (value / maxShift) * 100)}%` }} />
            </div>
            <strong>{formatMaybe(value, 2)}</strong>
          </div>
        );
      })}
    </div>
  );
}

function InterpretationGroup({
  title,
  rows,
  tone,
  description,
}: {
  title: string;
  rows: ChannelUpdate[];
  tone: "green" | "amber" | "orange" | "violet" | "blue";
  description: string;
}) {
  return (
    <section className={`pvp-summary-group pvp-summary-group--${tone}`}>
      <span className="pvp-group-status" aria-hidden="true" />
      <div>
        <h4>{title}</h4>
        <strong>{channelsText(rows)}</strong>
        <p>{description}</p>
      </div>
    </section>
  );
}

export function PriorVsPosteriorPage() {
  const result = useCurrentResult();
  const { payload } = result;
  const table = payload.roi_prior_posterior_table;
  const points = parsePosteriorRows(table?.rows);
  const channelRows = classifyChannels(points);
  const sensitivityCut = percentile(channelRows.map((row) => row.sensitivity), 0.75);
  const sensitiveRows = channelRows.filter((row) => row.sensitivity !== null && sensitivityCut !== null && row.sensitivity >= sensitivityCut);
  const strongRows = channelRows.filter((row) => row.strength === "Strong");
  const moderateRows = channelRows.filter((row) => row.strength === "Moderate");
  const weakRows = channelRows.filter((row) => row.strength === "Weak");
  const riskGroups = sensitivityRiskGroups(channelRows);
  const followUpCount = new Set([...weakRows, ...sensitiveRows].map((row) => row.channel)).size;
  const metricLabel = payload.outcome_context?.metric_label || "Revenue-equivalent ROI";
  const revenueValue = toNumber(payload.outcome_context?.revenue_per_kpi);
  const kpiSubtitle = payload.outcome_context
    ? `${payload.outcome_context.kpi_type || "KPI"} KPI -> revenue_value=${revenueValue === null ? "NA" : formatNumber(revenueValue, 2)}`
    : "Unavailable";
  const confidence = interpretationConfidence(payload);

  return (
    <SectionScaffold
      title="Prior vs Posterior"
      summary="Evidence of how strongly the data updated each channel's prior assumptions."
      sourceLabel={result.sourceLabel}
      sourceDetail={result.sourceDetail}
      sourceKind={result.sourceKind}
      activeRunId={result.activeRunId}
      runSummary={result.runSummary}
      buildResultsPath={result.buildResultsPath}
      headerAside={null}
    >
      <section className="pvp-summary-grid">
        <SummaryCard title="Channels with Strong Prior Updating" value={points.length ? String(strongRows.length) : "NA"} subtitle="Updated meaningfully by the data" />
        <SummaryCard title="Channels Needing Follow-up" value={points.length ? String(followUpCount) : "NA"} subtitle="Weak updates or high sensitivity" />
        <SummaryCard title="Median Posterior Shift" value={formatMaybe(median(channelRows.map((row) => row.avgAbsShift)), 2)} subtitle="Median of avg abs shift across channels" />
        <SummaryCard title="KPI Path" value={metricLabel} subtitle={kpiSubtitle} />
      </section>

      <section className="pvp-main-grid">
        <div className="pvp-left-stack">
          <article className="content-panel pvp-chart-card">
            <div className="pvp-card-title">
              <div className="pvp-card-heading">
                <h3>ROI Prior vs Posterior with 50% Posterior Intervals</h3>
                <p>Shows how posterior ROI estimates move under different prior assumptions.</p>
              </div>
              <div className="inline-help-row">
                <ContextualHelpButton sectionId="prior-posterior-chart" label="Open contextual help for this chart" />
                <InfoPopover label="Explain ROI prior vs posterior chart">
                  <p>This chart compares how each channel's posterior ROI changes under different prior assumptions.</p>
                  <ul>
                    <li>Colored points = posterior mean by prior variant</li>
                    <li>Colored lines = 50% posterior interval</li>
                    <li>Gray diamond = channel prior mean</li>
                    <li>Dashed vertical line = ROI 1.0 reference</li>
                  </ul>
                </InfoPopover>
              </div>
            </div>
            {table?.available === false ? <EmptyState message={table.reason || "Prior-vs-posterior table unavailable in this payload."} /> : <PriorPosteriorChart points={points} metricLabel={metricLabel} />}
          </article>

          <ConfidenceCard confidence={confidence} />
        </div>

        <aside className="content-panel pvp-interpretation-card">
          <div className="pvp-card-title">
            <h3>Prior-Updating Summary</h3>
          </div>
          {points.length ? (
            <>
              <section className="pvp-interpretation-section">
                <h4>Data Update Strength</h4>
                <p>How much the data moved posterior ROI away from the baseline prior.</p>
                <InterpretationGroup title="Strong data update" rows={strongRows} tone="green" description="Posteriors moved meaningfully." />
                <InterpretationGroup title="Moderate data update" rows={moderateRows} tone="amber" description="Visible movement, with some overlap." />
                <InterpretationGroup title="Weak data update" rows={weakRows} tone="orange" description="Limited movement from priors." />
              </section>
              <section className="pvp-interpretation-section">
                <h4>Prior Sensitivity Risk</h4>
                <p>How much posterior ROI varies across the tested prior grid.</p>
                <InterpretationGroup title="High sensitivity" rows={riskGroups.High} tone="violet" description="Conclusion shifts more across priors." />
                <InterpretationGroup title="Medium sensitivity" rows={riskGroups.Medium} tone="blue" description="Some dependence on prior choice." />
                <InterpretationGroup title="Low sensitivity" rows={riskGroups.Low} tone="green" description="Conclusion is comparatively stable." />
              </section>
            </>
          ) : (
            <EmptyState message="No posterior evidence rows are available for grouping." />
          )}
        </aside>
      </section>

      <section className="pvp-bottom-grid">
        <article className="content-panel pvp-shift-card">
          <div className="pvp-card-title pvp-card-title--stacked">
            <h3>Channel-by-Channel Shift</h3>
            <p>Average absolute posterior shift from the baseline prior.</p>
          </div>
          <ShiftChart rows={channelRows} />
        </article>

        <article className="content-panel pvp-stability-card">
          <div className="pvp-card-title">
            <h3>Posterior Stability Summary</h3>
            <div className="inline-help-row">
              <ContextualHelpButton sectionId="posterior-interval" label="Open contextual help for posterior intervals" />
              <InfoPopover label="Explain posterior stability summary table">
                <ul>
                  <li>Baseline Posterior ROI = posterior mean from the baseline prior variant.</li>
                  <li>ROI Range Across Priors = minimum to maximum posterior mean across tested prior variants.</li>
                  <li>Max Shift = largest absolute movement from the baseline posterior ROI.</li>
                  <li>50% CI Width = average width of the posterior 50% interval.</li>
                  <li>Stability summarizes whether the posterior conclusion stays similar as priors change.</li>
                </ul>
              </InfoPopover>
            </div>
          </div>
          {channelRows.length ? (
            <div className="table-shell">
              <table className="pvp-stability-table">
                <thead>
                  <tr>
                    <th>Channel</th>
                    <th>Baseline Posterior ROI</th>
                    <th>ROI Range Across Priors</th>
                    <th>Max Shift</th>
                    <th>50% CI Width</th>
                    <th>Stability</th>
                  </tr>
                </thead>
                <tbody>
                  {[...channelRows]
                    .sort((a, b) => Number(b.maxShift ?? b.ciWidth ?? -1) - Number(a.maxShift ?? a.ciWidth ?? -1))
                    .map((row) => (
                      <tr key={row.channel}>
                        <td>{titleCase(row.channel)}</td>
                        <td>{formatMaybe(row.baselinePosterior, 2)}</td>
                        <td>{formatRange(row.roiMin, row.roiMax)}</td>
                        <td>{formatMaybe(row.maxShift, 2)}</td>
                        <td>{formatMaybe(row.ciWidth, 2)}</td>
                        <td>
                          <span className={`pvp-stability-pill pvp-stability-pill--${stabilityClass(row.stability)}`}>{row.stability}</span>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState message="Posterior stability metrics are unavailable because posterior evidence rows are missing." />
          )}
        </article>
      </section>
    </SectionScaffold>
  );
}
