import { SectionScaffold } from "../components/SectionScaffold";
import { useCurrentResult } from "../data/resultLoader";
import { formatNumber, selectResultSectionCounts } from "../data/resultSelectors";

export function PriorVsPosteriorPage() {
  const result = useCurrentResult();
  const { payload } = result;
  const counts = selectResultSectionCounts(payload);
  const table = payload.roi_prior_posterior_table;

  return (
    <SectionScaffold
      title="Results / Prior vs Posterior"
      summary="Compare fixed-grid ROI prior assumptions against posterior evidence from the completed audit outputs."
      sourceLabel={result.sourceLabel}
      sourceDetail={result.sourceDetail}
      sourceKind={result.sourceKind}
    >
      <section className="content-panel">
        <div className="section-title-row">
          <div>
            <span className="eyebrow">Evidence figure</span>
            <h3>ROI prior vs posterior intervals</h3>
          </div>
          <span className="subtle-chip">{formatNumber(counts.posteriorEvidenceRows)} table rows</span>
        </div>
        {result.assets.roiPriorPosteriorFigure ? (
          <div className="figure-frame">
            <img src={result.assets.roiPriorPosteriorFigure} alt="ROI prior vs posterior with posterior intervals" />
          </div>
        ) : (
          <p className="muted">No prior-vs-posterior figure asset is available for this run-specific results route.</p>
        )}
        {table?.available === false ? <p className="muted">{table.reason || "Prior vs posterior table unavailable in this payload."}</p> : null}
      </section>

      <section className="content-panel">
        <h3>Payload Section Status</h3>
        <p className="muted">
          The generated figure is available from the existing report assets. The table payload currently exposes {formatNumber(counts.posteriorEvidenceRows)} row(s), so this page keeps the figure as the primary artifact.
        </p>
      </section>
    </SectionScaffold>
  );
}
