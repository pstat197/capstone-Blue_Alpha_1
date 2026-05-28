import { MetricCard } from "../components/MetricCard";
import { SectionScaffold } from "../components/SectionScaffold";
import { TornadoChart } from "../components/TornadoChart";
import { ContextualHelpButton } from "../../../shared/ContextualHelp";
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
  const movementValue = formatMovementValue(largestMovement);
  const movementValueSize = movementValue.length >= 7 ? "extra-long" : movementValue.length >= 6 ? "long" : "standard";
  const roundedRobustnessScore = Number.isFinite(Number(payload.decision_card?.score_numeric))
    ? Math.round(Number(payload.decision_card?.score_numeric))
    : null;
  const robustnessBand =
    roundedRobustnessScore === null
      ? "available"
      : roundedRobustnessScore >= 70
        ? "higher"
        : roundedRobustnessScore >= 40
          ? "medium"
          : "lower";
  const interpretationNotes = [
    stats.failRuns === 0 && stats.reviewRuns > 0
      ? `All ${formatNumber(stats.completedRuns)} completed runs were flagged for REVIEW, not FAIL. This means the audit is usable for directional sensitivity analysis, but not yet strong enough for budget-level decisions.`
      : `The completed run set produced PASS ${formatNumber(stats.passRuns)}, REVIEW ${formatNumber(stats.reviewRuns)}, and FAIL ${formatNumber(stats.failRuns)} outcomes. Use the review mix to judge how directional these findings should be.`,
    roundedRobustnessScore === null
      ? "The overall robustness score is available in the technical details and should be reviewed before making budget-level decisions."
      : `The overall robustness score is ${roundedRobustnessScore}/100, which indicates ${robustnessBand} stability across the tested prior settings.`,
    "Some percentage-change metrics were unstable because baseline ROI was sensitive for several channel-prior pairs. For those cases, movement is ranked using absolute Delta ROI instead of percent change.",
    "The largest movers should be treated as prior-sensitivity findings, not automatic budget recommendations.",
  ];
  const cautionFlags = [
    "Avoid hard budget shifts from this run alone.",
    "Treat the largest channel movements as audit signals that need follow-up review.",
    "Recalibrate priors or review QC issues before making strong percent-change claims.",
    "Use the Prior Sensitivity page to inspect target-level robustness before drawing final conclusions.",
  ];
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
        <div className="metric-card-with-help">
          <MetricCard
            label="QC Pass Rate"
            value={formatPercent(stats.passRatePct, 1)}
            note={`PASS ${stats.passRuns} / REVIEW ${stats.reviewRuns} / FAIL ${stats.failRuns}`}
          />
          <ContextualHelpButton sectionId="qc-pass-rate" label="Explain QC pass rate" />
        </div>
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
          <p className={`large-stat large-stat--${movementValueSize}`}>{movementValue}</p>
          <p className="muted">Largest {movementDescriptor} in the completed self-response audit.</p>
          <p className="supporting-line">{baselineText}</p>
        </div>

        <div className="content-panel movement-card">
          <div className="section-title-row">
            <div>
              <div className="movement-card__title-row">
                <h3>Movement by Channel</h3>
                <span className="subtle-chip">Showing: {stats.metricLabel}</span>
              </div>
              <p className="movement-card__subtitle">
                Channel movement is measured against baseline ROI after converting the non-revenue KPI into revenue-equivalent value.
              </p>
            </div>
            <div className="inline-help-row">
              <ContextualHelpButton sectionId="movement-chart" label="Explain movement by channel" />
            </div>
          </div>
          <TornadoChart rows={tornadoRows} compact />
        </div>

        <div className="content-panel diagnostic-card">
          <div className="section-title-row section-title-row--compact">
            <h3>Diagnostic Interpretation</h3>
            <ContextualHelpButton sectionId="interpretation-tier" label="Explain diagnostic interpretation" />
          </div>
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
            {interpretationNotes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </div>
        <div className="content-panel result-list-card">
          <div className="section-title-row section-title-row--compact">
            <h3>Caution Flags</h3>
            <ContextualHelpButton sectionId="caution-flags" label="Explain caution flags" />
          </div>
          <ul className="dashboard-list dashboard-list--warning">
            {cautionFlags.map((flag) => (
              <li key={flag}>{flag}</li>
            ))}
          </ul>
        </div>
      </section>
    </SectionScaffold>
  );
}
