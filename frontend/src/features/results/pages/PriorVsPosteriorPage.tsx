import { SectionScaffold } from "../components/SectionScaffold";
import { useCurrentResult } from "../data/resultLoader";
import { formatNumber } from "../data/resultSelectors";

type PosteriorPoint = {
  channel: string;
  variant: string;
  variantShort: string;
  mu: number | null;
  sigma: number | null;
  mean: number;
  lower50: number;
  upper50: number;
};

type ChannelUpdate = {
  channel: string;
  avgPosterior: number | null;
  ciWidth: number | null;
  sensitivity: number | null;
  avgAbsShift: number | null;
  strength: "Strong" | "Moderate" | "Weak" | "Unavailable";
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
        mu: toNumber(row.prior_roi_mu),
        sigma: toNumber(row.prior_roi_sigma),
        mean,
        lower50,
        upper50,
      };
    })
    .filter((row): row is PosteriorPoint => Boolean(row));
}

function nearestBaseline(points: PosteriorPoint[]): PosteriorPoint | null {
  const withPrior = points.filter((point) => point.mu !== null || point.sigma !== null);
  const candidates = withPrior.length ? withPrior : points;
  return [...candidates].sort((a, b) => {
    const aScore = Math.abs((a.mu ?? 1) - 1) + Math.abs((a.sigma ?? 1) - 1);
    const bScore = Math.abs((b.mu ?? 1) - 1) + Math.abs((b.sigma ?? 1) - 1);
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
    const sortedMeans = [...means].sort((a, b) => a - b);
    const q1 = percentile(sortedMeans, 0.25);
    const q3 = percentile(sortedMeans, 0.75);
    return {
      channel,
      avgPosterior: means.reduce((sum, value) => sum + value, 0) / means.length,
      ciWidth: channelPoints.reduce((sum, point) => sum + (point.upper50 - point.lower50), 0) / channelPoints.length,
      sensitivity: q1 !== null && q3 !== null ? q3 - q1 : null,
      avgAbsShift,
      strength: "Unavailable" as ChannelUpdate["strength"],
    };
  });

  const weakCut = percentile(baseRows.map((row) => row.avgAbsShift), 0.33);
  const strongCut = percentile(baseRows.map((row) => row.avgAbsShift), 0.67);

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
      return { ...row, strength };
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

function EmptyState({ message }: { message: string }) {
  return <div className="pvp-empty-state">{message}</div>;
}

function SummaryCard({
  icon,
  title,
  value,
  subtitle,
  tone,
}: {
  icon: string;
  title: string;
  value: string;
  subtitle: string;
  tone: "blue" | "amber" | "violet" | "navy";
}) {
  return (
    <article className="pvp-summary-card">
      <span className={`pvp-summary-icon pvp-summary-icon--${tone}`} aria-hidden="true">
        {icon}
      </span>
      <div>
        <h3>{title}</h3>
        <strong>{value}</strong>
        <p>{subtitle}</p>
      </div>
    </article>
  );
}

function PriorPosteriorChart({ points, metricLabel }: { points: PosteriorPoint[]; metricLabel: string }) {
  if (!points.length) return <EmptyState message="Prior-vs-posterior rows are unavailable for this run." />;

  const channels = [...new Set(points.map((point) => point.channel))];
  const variants = [...new Set(points.map((point) => point.variantShort))];
  const values = points.flatMap((point) => [point.lower50, point.upper50, point.mean, point.mu ?? 1]);
  const minValue = Math.min(0, ...values);
  const maxValue = Math.max(1, ...values);
  const span = maxValue - minValue || 1;
  const width = 820;
  const rowHeight = 38;
  const top = 28;
  const left = 104;
  const right = 26;
  const bottom = 48;
  const plotWidth = width - left - right;
  const height = top + channels.length * rowHeight + bottom;
  const x = (value: number) => left + ((value - minValue) / span) * plotWidth;
  const ticks = Array.from({ length: 6 }, (_, idx) => minValue + (span * idx) / 5);
  const baselineX = x(1);

  return (
    <div className="pvp-chart-shell">
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
                return (
                  <g key={`${channel}-${point.variantShort}`}>
                    <line x1={x(point.lower50)} x2={x(point.upper50)} y1={y} y2={y} stroke={color} strokeWidth="2.2" opacity="0.78" />
                    <line x1={x(point.lower50)} x2={x(point.lower50)} y1={y - 3} y2={y + 3} stroke={color} strokeWidth="1.6" opacity="0.72" />
                    <line x1={x(point.upper50)} x2={x(point.upper50)} y1={y - 3} y2={y + 3} stroke={color} strokeWidth="1.6" opacity="0.72" />
                    <circle cx={x(point.mean)} cy={y} r="4" fill={color} stroke="#ffffff" strokeWidth="1.4" />
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
      <aside className="pvp-legend-card">
        <h4>Prior Variants</h4>
        <div className="pvp-legend-list">
          {variants.map((variant, index) => (
            <div className="pvp-legend-item" key={variant}>
              <span style={{ background: variantColors[index % variantColors.length] }} />
              <b>{variant}</b>
            </div>
          ))}
        </div>
        <p>Points = posterior mean<br />Lines = 50% interval</p>
      </aside>
    </div>
  );
}

function ShiftChart({ rows }: { rows: ChannelUpdate[] }) {
  const validRows = rows.filter((row) => row.avgAbsShift !== null);
  if (!validRows.length) return <EmptyState message="Baseline prior rows are unavailable, so channel shift cannot be calculated." />;
  const maxShift = Math.max(...validRows.map((row) => row.avgAbsShift || 0)) || 1;
  return (
    <div className="pvp-shift-bars">
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

function SummaryGroup({
  title,
  rows,
  tone,
  description,
}: {
  title: string;
  rows: ChannelUpdate[];
  tone: "green" | "amber" | "orange" | "violet";
  description: string;
}) {
  return (
    <section className={`pvp-summary-group pvp-summary-group--${tone}`}>
      <span className="pvp-group-status" aria-hidden="true" />
      <div>
        <h4>
          {title} ({rows.length})
        </h4>
        <strong>{rows.length ? rows.map((row) => titleCase(row.channel)).join(", ") : "Unavailable"}</strong>
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
  const followUpCount = new Set([...weakRows, ...sensitiveRows].map((row) => row.channel)).size;
  const metricLabel = payload.outcome_context?.metric_label || "Revenue-equivalent ROI";
  const revenueValue = toNumber(payload.outcome_context?.revenue_per_kpi);
  const kpiSubtitle = payload.outcome_context
    ? `${payload.outcome_context.kpi_type || "KPI"} KPI -> revenue_value=${revenueValue === null ? "NA" : formatNumber(revenueValue, 2)}`
    : "Unavailable";
  const confidence = confidenceFromPayload(payload);

  return (
    <SectionScaffold
      title="Results / Prior vs Posterior"
      summary="Evidence of how strongly the data updated each channel's prior assumptions."
      sourceLabel={result.sourceLabel}
      sourceDetail={result.sourceDetail}
      sourceKind={result.sourceKind}
      activeRunId={result.activeRunId}
      runSummary={result.runSummary}
      buildResultsPath={result.buildResultsPath}
      headerAside={
        <div className="pvp-header-controls">
          <button type="button" className="pvp-control-chip">
            <span aria-hidden="true">↗</span>
            {metricLabel}
          </button>
          <button type="button" className="pvp-control-chip pvp-control-chip--export">
            <span aria-hidden="true">⇩</span>
            Export
            <span aria-hidden="true">⌄</span>
          </button>
        </div>
      }
    >
      <section className="pvp-summary-grid">
        <SummaryCard icon="◎" tone="blue" title="Channels with Strong Prior Updating" value={points.length ? String(strongRows.length) : "NA"} subtitle="Updated meaningfully by the data" />
        <SummaryCard icon="△" tone="amber" title="Channels Needing Follow-up" value={points.length ? String(followUpCount) : "NA"} subtitle="Weak updates or high sensitivity" />
        <SummaryCard icon="↗" tone="violet" title="Median Posterior Shift" value={formatMaybe(median(channelRows.map((row) => row.avgAbsShift)), 2)} subtitle="Median of avg abs shift across channels" />
        <SummaryCard icon="KPI" tone="navy" title="KPI Path" value={metricLabel} subtitle={kpiSubtitle} />
      </section>

      <section className="pvp-main-grid">
        <article className="content-panel pvp-chart-card">
          <div className="pvp-card-title">
            <h3>ROI Prior vs Posterior with 50% Posterior Intervals</h3>
            <span>i</span>
          </div>
          {table?.available === false ? <EmptyState message={table.reason || "Prior-vs-posterior table unavailable in this payload."} /> : <PriorPosteriorChart points={points} metricLabel={metricLabel} />}
        </article>

        <aside className="content-panel pvp-interpretation-card">
          <div className="pvp-card-title">
            <h3>Prior-Updating Summary</h3>
            <span>i</span>
          </div>
          {points.length ? (
            <>
              <SummaryGroup title="Strongly updated" rows={strongRows} tone="green" description="Posteriors moved meaningfully across tested prior variants." />
              <SummaryGroup title="Moderately updated" rows={moderateRows} tone="amber" description="Some movement across priors, with partial overlap." />
              <SummaryGroup title="Weakly updated" rows={weakRows} tone="orange" description="Posteriors remain comparatively clustered with minimal movement." />
              <SummaryGroup title="Most prior-sensitive channels" rows={sensitiveRows} tone="violet" description="Show wider posterior movement under alternative priors." />
              <div className={`pvp-confidence pvp-confidence--${confidence.toLowerCase()}`}>
                Interpretation confidence: <strong>{confidence}</strong>
              </div>
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
            <h3>Interval Overlap &amp; Stability</h3>
            <span>i</span>
          </div>
          {channelRows.length ? (
            <div className="table-shell">
              <table className="pvp-stability-table">
                <thead>
                  <tr>
                    <th>Channel</th>
                    <th>Avg Posterior ROI</th>
                    <th>CI Width</th>
                    <th>Prior Sensitivity</th>
                    <th>Update Strength</th>
                  </tr>
                </thead>
                <tbody>
                  {[...channelRows]
                    .sort((a, b) => Number(b.avgAbsShift ?? b.sensitivity ?? -1) - Number(a.avgAbsShift ?? a.sensitivity ?? -1))
                    .map((row) => (
                      <tr key={row.channel}>
                        <td>{titleCase(row.channel)}</td>
                        <td>{formatMaybe(row.avgPosterior, 2)}</td>
                        <td>{formatMaybe(row.ciWidth, 2)}</td>
                        <td>{formatMaybe(row.sensitivity, 2)}</td>
                        <td>
                          <span className={`pvp-strength-pill pvp-strength-pill--${row.strength.toLowerCase()}`}>{row.strength}</span>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState message="Interval stability metrics are unavailable because posterior evidence rows are missing." />
          )}
        </article>
      </section>
    </SectionScaffold>
  );
}
