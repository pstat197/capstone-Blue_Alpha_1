import { MetricCard } from "../components/MetricCard";
import { SectionScaffold } from "../components/SectionScaffold";
import { useCurrentResult } from "../data/resultLoader";
import { formatNumber, selectResultSectionCounts, selectStructuralProfileRows, selectStructuralRunRows } from "../data/resultSelectors";

export function ModelStructurePage() {
  const result = useCurrentResult();
  const { payload } = result;
  const counts = selectResultSectionCounts(payload);
  const structural = payload.structural;
  const profiles = selectStructuralProfileRows(payload);
  const structuralRuns = selectStructuralRunRows(payload);

  return (
    <SectionScaffold
      title="Results / Model Structure"
      summary="Review computed structural settings and run evidence from the completed audit."
      sourceLabel={result.sourceLabel}
      sourceDetail={result.sourceDetail}
      sourceKind={result.sourceKind}
    >
      <section className="overview-hero-grid overview-hero-grid--compact">
        <MetricCard label="Structural profiles" value={formatNumber(counts.structuralProfiles)} note="structural.profile_rows" />
        <MetricCard label="Structural runs" value={formatNumber(counts.structuralRuns)} note="structural.run_rows" />
        <MetricCard label="Selected profile" value={structural?.selected_profile_id || "Unavailable"} />
      </section>

      <section className="content-panel">
        <h3>Structural Profile</h3>
        <div className="table-shell">
          <table>
            <thead>
              <tr>
                <th>Adstock alpha</th>
                <th>EC</th>
                <th>Slope</th>
                <th>Max lag</th>
                <th>Immediate share</th>
                <th>Carryover share</th>
              </tr>
            </thead>
            <tbody>
              {profiles.map((row) => (
                <tr key={String(row.struct_profile_id)}>
                  <td>{String(row.adstock_alpha_m || "Unavailable")}</td>
                  <td>{String(row.saturation_ec_m || "Unavailable")}</td>
                  <td>{String(row.saturation_slope_m || "Unavailable")}</td>
                  <td>{String(row.max_lag || "Unavailable")}</td>
                  <td>{String(row.immediate_share || "Unavailable")}</td>
                  <td>{String(row.carryover_share || "Unavailable")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="result-grid">
        <div className="content-panel">
          <h3>Model Structure Notes</h3>
          <ul className="compact-list">
            {(structural?.notes || []).slice(0, 3).map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </div>
        <div className="content-panel">
          <h3>Structural Run Sample</h3>
          <div className="mini-row-list">
            {structuralRuns.slice(0, 4).map((row) => (
              <div className="mini-row" key={String(row.run_id)}>
                <span>mu {String(row.roi_prior_mu)} / sigma {String(row.roi_prior_sigma)}</span>
                <strong>{String(row.qc_status_code || "Unavailable")}</strong>
              </div>
            ))}
          </div>
        </div>
      </section>
    </SectionScaffold>
  );
}
