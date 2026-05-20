import { MetricCard } from "../components/MetricCard";
import { SectionScaffold } from "../components/SectionScaffold";
import { TornadoChart } from "../components/TornadoChart";
import { useCurrentResult } from "../data/resultLoader";
import {
  channelLabel,
  formatMovementValue,
  formatNumber,
  formatPercent,
  selectDiagnosticContext,
  selectLargestSelfResponse,
  selectOverviewStats,
  selectResultHeader,
  selectRunScope,
  selectSelfResponseTornadoRows,
} from "../data/resultSelectors";

export function OverviewPage() {
  const result = useCurrentResult();
  const payload = result.payload;
  const header = selectResultHeader(payload);
  const stats = selectOverviewStats(payload);
  const runScope = selectRunScope(payload);
  const largestMovement = selectLargestSelfResponse(payload);
  const tornadoRows = selectSelfResponseTornadoRows(payload);
  const diagnostic = selectDiagnosticContext(payload);
  const primaryMetricIsDelta = String(largestMovement?.primary_metric || "").toLowerCase().includes("delta");
  const movementDescriptor = primaryMetricIsDelta ? "max |Delta ROI|" : "fixed-grid movement";
  const baselineText =
    largestMovement?.baseline_roi !== undefined
      ? `Baseline ROI ${formatNumber(largestMovement.baseline_roi, 3)} under ${largestMovement.roi_prior_dist || "Not available"} prior.`
      : "Baseline context not available.";

  return (
    <SectionScaffold
      title="Overview"
      summary="Summary of completed prior sensitivity outputs and key audit signals."
      sourceLabel={result.sourceLabel}
      sourceDetail={result.sourceDetail}
      sourceKind={result.sourceKind}
      activeRunId={result.activeRunId}
      runSummary={result.runSummary}
      buildResultsPath={result.buildResultsPath}
      headerAside={null}
    >
      <section className="summary-metric-row" aria-label="Completed run summary">
        <MetricCard label="Completed Runs" value={formatNumber(stats.completedRuns)} note={`Generated ${header.generatedAt}`} />
        <MetricCard label="Channels" value={formatNumber(stats.modeledChannels)} note="Active channels" />
        <MetricCard
          label="QC Pass Rate"
          value={formatPercent(stats.passRatePct, 1)}
          note={`PASS ${stats.passRuns} / REVIEW ${stats.reviewRuns} / FAIL ${stats.failRuns}`}
        />
        <MetricCard
          label="KPI Path"
          value={stats.metricLabel}
          note={`${stats.kpiType} KPI -> ${stats.effectiveKpiType}${stats.revenuePerKpi ? `, value=${formatNumber(stats.revenuePerKpi, 2)}` : ""}`}
        />
        <MetricCard label="Run Type / Scope" value={runScope.value} note={runScope.note} />
      </section>

      <section className="overview-insight-grid" aria-label="Main result insights">
        <div className="content-panel overview-main-card overview-main-card--primary">
          <span className="eyebrow">Largest Self-Response Movement</span>
          <h3>{channelLabel(largestMovement?.channel)}</h3>
          <p className="large-stat">{formatMovementValue(largestMovement)}</p>
          <p className="muted">Largest {movementDescriptor} in the completed self-response audit.</p>
          <p className="supporting-line">{baselineText}</p>
        </div>

        <div className="content-panel movement-card">
          <div className="section-title-row">
            <div>
              <h3>Movement by Channel</h3>
            </div>
            <span className="subtle-chip">{stats.metricLabel}</span>
          </div>
          <TornadoChart rows={tornadoRows} compact />
        </div>

        <div className="content-panel diagnostic-card">
          <h3>Diagnostic Interpretation</h3>
          <div className={`diagnostic-status diagnostic-status--${String(diagnostic.tier).toLowerCase()}`}>
            <span aria-hidden="true" />
            <strong>{diagnostic.tier}</strong>
          </div>
          <div className="diagnostic-callout">
            <span aria-hidden="true" />
            <p>{diagnostic.headline}</p>
          </div>
          <div className="review-check">
            <strong>Primary review check:</strong>
            <span>{diagnostic.primaryReviewCheck} across {formatNumber(diagnostic.reviewCount)} review runs.</span>
          </div>
        </div>
      </section>

      <section className="interpretation-grid">
        <div className="content-panel result-list-card">
          <h3>Interpretation Notes</h3>
          <ul className="dashboard-list dashboard-list--info">
            {diagnostic.interpretationNotes.slice(0, 4).map((note) => (
              <li key={note}>{note}</li>
            ))}
            {!diagnostic.interpretationNotes.length ? <li>Not available</li> : null}
          </ul>
        </div>
        <div className="content-panel result-list-card">
          <h3>Caution Flags</h3>
          <ul className="dashboard-list dashboard-list--warning">
            {diagnostic.cautionFlags.slice(0, 4).map((flag) => (
              <li key={flag}>{flag}</li>
            ))}
            {!diagnostic.cautionFlags.length ? <li>Not available</li> : null}
          </ul>
        </div>
      </section>
    </SectionScaffold>
  );
}
