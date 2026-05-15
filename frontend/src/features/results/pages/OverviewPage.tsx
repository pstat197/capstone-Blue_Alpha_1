import { MetricCard } from "../components/MetricCard";
import { SectionScaffold } from "../components/SectionScaffold";
import { TornadoChart } from "../components/TornadoChart";
import { useCurrentResult } from "../data/resultLoader";
import {
  channelLabel,
  formatNumber,
  formatPercent,
  selectDiagnosticContext,
  selectLargestSelfResponse,
  selectOverviewStats,
  selectResultHeader,
  selectSelfResponseTornadoRows,
} from "../data/resultSelectors";

export function OverviewPage() {
  const result = useCurrentResult();
  const payload = result.payload;
  const header = selectResultHeader(payload);
  const stats = selectOverviewStats(payload);
  const largestMovement = selectLargestSelfResponse(payload);
  const tornadoRows = selectSelfResponseTornadoRows(payload);
  const diagnostic = selectDiagnosticContext(payload);

  return (
    <SectionScaffold
      title="Results / Overview"
      summary="Fixed-grid prior sensitivity audit: identify the largest movement, then interpret it through diagnostic context."
      sourceLabel={result.sourceLabel}
      sourceDetail={result.sourceDetail}
      sourceKind={result.sourceKind}
    >
      <section className="executive-overview" aria-label="Fixed-grid audit overview">
        <div className="content-panel overview-main-card overview-main-card--primary">
          <span className="eyebrow">Largest self-response movement</span>
          <h3>{channelLabel(largestMovement?.channel)}</h3>
          <p className="large-stat">{formatPercent(largestMovement?.primary_value ?? largestMovement?.max_abs_pct_change, 2)}</p>
          <p className="muted">
            Largest fixed-grid movement in the completed self-response audit. Baseline ROI {formatNumber(largestMovement?.baseline_roi, 3)} under{" "}
            {largestMovement?.roi_prior_dist || "Unavailable"} prior.
          </p>
        </div>

        <div className="executive-side-stack">
          <MetricCard label="Completed runs" value={formatNumber(stats.completedRuns)} note={`${formatNumber(stats.modeledChannels)} channels; generated ${header.generatedAt}`} />
          <MetricCard
            label="QC pass rate"
            value={formatPercent(stats.passRatePct, 1)}
            note={`PASS ${stats.passRuns} / REVIEW ${stats.reviewRuns} / FAIL ${stats.failRuns}`}
          />
          <MetricCard
            label="KPI path"
            value={stats.metricLabel}
            note={`${stats.kpiType} KPI -> ${stats.effectiveKpiType}${stats.revenuePerKpi ? `, value=${formatNumber(stats.revenuePerKpi, 2)}` : ""}`}
          />
        </div>
      </section>

      <section className="result-grid result-grid--overview">
        <div className="content-panel">
          <div className="section-title-row">
            <div>
              <span className="eyebrow">Self-response tornado</span>
              <h3>Movement by channel</h3>
            </div>
            <span className="subtle-chip">{stats.metricLabel}</span>
          </div>
          <TornadoChart rows={tornadoRows} compact />
        </div>

        <div className="content-panel overview-main-card">
          <span className="eyebrow">Diagnostic interpretation</span>
          <h3>{diagnostic.tier}</h3>
          <p>{diagnostic.headline}</p>
          <p className="muted">Primary review check: {diagnostic.primaryReviewCheck} across {formatNumber(diagnostic.reviewCount)} review runs.</p>
        </div>
      </section>

      <section className="content-panel">
        <div className="section-title-row">
          <div>
            <span className="eyebrow">How to read this result</span>
            <h3>Directional interpretation of the completed fixed grid</h3>
          </div>
        </div>
        <div className="interpretation-grid">
          <div>
            <h4>Interpretation Notes</h4>
            <ul className="compact-list">
              {diagnostic.interpretationNotes.slice(0, 4).map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </div>
          <div>
            <h4>Caution Flags</h4>
            <ul className="compact-list">
              {diagnostic.cautionFlags.slice(0, 4).map((flag) => (
                <li key={flag}>{flag}</li>
              ))}
            </ul>
          </div>
        </div>
      </section>
    </SectionScaffold>
  );
}
