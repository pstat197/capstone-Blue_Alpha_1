import { MetricCard } from "../components/MetricCard";
import { SectionScaffold } from "../components/SectionScaffold";
import { TornadoChart } from "../components/TornadoChart";
import { useCurrentResult } from "../data/resultLoader";
import {
  channelLabel,
  formatMoneyCompact,
  formatNumber,
  formatPercent,
  selectDollarTornadoRows,
  selectResultSectionCounts,
  selectSelfResponseTornadoRows,
} from "../data/resultSelectors";

export function PriorSensitivityPage() {
  const result = useCurrentResult();
  const { payload } = result;
  const counts = selectResultSectionCounts(payload);
  const tornadoRows = selectSelfResponseTornadoRows(payload);
  const dollarRows = selectDollarTornadoRows(payload);

  return (
    <SectionScaffold
      title="Results / Prior Sensitivity"
      summary="Read-only view of which channels moved most across the completed fixed ROI-prior grid."
      sourceLabel={result.sourceLabel}
      sourceDetail={result.sourceDetail}
      sourceKind={result.sourceKind}
    >
      <section className="content-panel">
        <div className="section-title-row">
          <div>
            <span className="eyebrow">Full-system prior response</span>
            <h3>Self-response tornado</h3>
          </div>
          <span className="subtle-chip">{formatNumber(counts.priorSensitivityRows)} ranking rows</span>
        </div>
        <TornadoChart rows={tornadoRows} />
      </section>

      <section className="overview-hero-grid overview-hero-grid--compact">
        <MetricCard label="Target channels" value={formatNumber(payload.target_channel_detail?.options?.length ?? 0)} note="Completed target set" />
        <MetricCard label="Default target" value={channelLabel(payload.target_channel_detail?.default_channel)} note="Initial result-page view" />
        <MetricCard label="Audit scope" value="Fixed grid" note={payload.target_channel_detail?.recommendation_source} />
      </section>

      <section className="content-panel">
        <h3>Top Dollar Sensitivity Rows</h3>
        <div className="table-shell">
          <table>
            <thead>
              <tr>
                <th>Channel</th>
                <th>Max abs dollar change</th>
                <th>Median dollar change</th>
                <th>N</th>
              </tr>
            </thead>
            <tbody>
              {dollarRows.slice(0, 6).map((row) => (
                <tr key={String(row.channel)}>
                  <td>{channelLabel(row.channel)}</td>
                  <td>{formatMoneyCompact(row.max_abs_dollar_change)}</td>
                  <td>{formatMoneyCompact(row.median_dollar_change)}</td>
                  <td>{formatNumber(row.n)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="content-panel">
        <h3>Prior Sensitivity Ranking</h3>
        <div className="table-shell">
          <table>
            <thead>
              <tr>
                <th>Channel</th>
                <th>Prior dist</th>
                <th>Baseline ROI</th>
                <th>Max abs movement</th>
              </tr>
            </thead>
            <tbody>
              {(payload.rank_rows || []).map((row) => (
                <tr key={`${row.channel}-${row.roi_prior_dist}`}>
                  <td>{channelLabel(row.channel)}</td>
                  <td>{row.roi_prior_dist || "Unavailable"}</td>
                  <td>{formatNumber(row.baseline_roi, 3)}</td>
                  <td>{formatPercent(row.primary_value ?? row.max_abs_pct_change, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </SectionScaffold>
  );
}
