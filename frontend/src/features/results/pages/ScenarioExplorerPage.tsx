import { MetricCard } from "../components/MetricCard";
import { SectionScaffold } from "../components/SectionScaffold";
import { useCurrentResult } from "../data/resultLoader";
import { channelLabel, formatNumber, formatPercent, selectResultSectionCounts, selectScenarioSnapshots } from "../data/resultSelectors";

export function ScenarioExplorerPage() {
  const result = useCurrentResult();
  const { payload } = result;
  const counts = selectResultSectionCounts(payload);
  const workbench = payload.workbench;
  const scenarios = selectScenarioSnapshots(payload);
  const firstScenarioRows = (scenarios[0]?.rows as Array<Record<string, unknown>> | undefined) || [];

  return (
    <SectionScaffold
      title="Results / Scenario Explorer"
      summary="Explore completed prior scenarios. Controls here are filters over existing rows, not new run configuration."
      sourceLabel={result.sourceLabel}
      sourceDetail={result.sourceDetail}
      sourceKind={result.sourceKind}
    >
      <section className="overview-hero-grid overview-hero-grid--compact">
        <MetricCard label="Completed scenario rows" value={formatNumber(counts.scenarioItems)} note="scenario_items or workbench.run_rows" />
        <MetricCard label="Available channels" value={formatNumber(workbench?.available_channels?.length ?? 0)} note={workbench?.available_channels?.join(", ")} />
        <MetricCard label="Mu values" value={formatNumber(workbench?.mu_values?.length ?? 0)} note={workbench?.mu_values?.join(", ")} />
        <MetricCard label="Sigma values" value={formatNumber(workbench?.sigma_values?.length ?? 0)} note={workbench?.sigma_values?.join(", ")} />
      </section>

      <section className="content-panel">
        <div className="section-title-row">
          <div>
            <span className="eyebrow">Scenario snapshot</span>
            <h3>{String(scenarios[0]?.label || "Completed prior scenario")}</h3>
          </div>
          <span className="subtle-chip">{formatNumber(firstScenarioRows.length)} channels</span>
        </div>
        <p className="muted">{workbench?.notes || "Workbench notes unavailable."}</p>
        <div className="table-shell">
          <table>
            <thead>
              <tr>
                <th>Channel</th>
                <th>Estimated ROI</th>
                <th>Baseline ROI</th>
                <th>% change</th>
                <th>Delta value</th>
              </tr>
            </thead>
            <tbody>
              {firstScenarioRows.map((row) => (
                <tr key={String(row.channel)}>
                  <td>{channelLabel(row.channel)}</td>
                  <td>{formatNumber(row.estimated_roi, 3)}</td>
                  <td>{formatNumber(row.baseline_roi, 3)}</td>
                  <td>{formatPercent(row.pct_change, 1)}</td>
                  <td>{String(row.delta_value_used || "Unavailable")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </SectionScaffold>
  );
}
