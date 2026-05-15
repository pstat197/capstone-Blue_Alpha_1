import { MetricCard } from "../components/MetricCard";
import { SectionScaffold } from "../components/SectionScaffold";
import { useCurrentResult } from "../data/resultLoader";
import { formatNumber, selectOverviewStats, selectResultSectionCounts } from "../data/resultSelectors";

export function RunAuditDiagnosticsPage() {
  const result = useCurrentResult();
  const { payload } = result;
  const counts = selectResultSectionCounts(payload);
  const stats = selectOverviewStats(payload);
  const audit = payload.how_this_was_run;

  return (
    <SectionScaffold
      title="Results / Run Audit & Diagnostics"
      summary="Read-only audit trail for the completed fixed-grid run: setup, QC mix, and diagnostic workflow."
      sourceLabel={result.sourceLabel}
      sourceDetail={result.sourceDetail}
      sourceKind={result.sourceKind}
    >
      <section className="overview-hero-grid overview-hero-grid--compact">
        <MetricCard label="PASS runs" value={formatNumber(stats.passRuns)} />
        <MetricCard label="REVIEW runs" value={formatNumber(stats.reviewRuns)} />
        <MetricCard label="FAIL runs" value={formatNumber(stats.failRuns)} />
        <MetricCard label="Audit badges" value={formatNumber(counts.auditBadges)} note="how_this_was_run.badges" />
      </section>

      <section className="content-panel">
        <h3>How This Was Run</h3>
        <p className="muted">{audit?.summary || "Run summary unavailable."}</p>
        <div className="badge-grid">
          {(audit?.badges || []).map((badge) => (
            <div className="summary-badge" key={`${badge.label}-${badge.value}`}>
              <span>{badge.label}</span>
              <strong>{badge.value}</strong>
            </div>
          ))}
        </div>
      </section>

      <section className="content-panel">
        <h3>Workflow Steps</h3>
        <ol className="compact-list">
          {(audit?.workflow_steps || []).map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      </section>
    </SectionScaffold>
  );
}
