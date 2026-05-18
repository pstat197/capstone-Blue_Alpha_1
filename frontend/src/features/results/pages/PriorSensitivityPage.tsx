import type { ReactNode } from "react";
import { SectionScaffold } from "../components/SectionScaffold";
import { useCurrentResult } from "../data/resultLoader";
import type { DashboardPayload, DollarTornadoRow, RankRow, RoiTornadoRow } from "../data/resultTypes";
import {
  channelLabel,
  formatMoneyCompact,
  formatMovementValue,
  formatNumber,
  formatPercent,
  selectDollarTornadoRows,
  selectRunScope,
  selectSelfResponseTornadoRows,
} from "../data/resultSelectors";

function downloadText(filename: string, text: string, type: string) {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function csvEscape(value: unknown): string {
  const text = value === null || value === undefined ? "" : String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function statusText(value: unknown): string {
  const text = String(value || "").trim();
  return text || "Unavailable";
}

function signedMoneyClass(value: unknown): string {
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) return "";
  return n > 0 ? "ps-value-positive" : "ps-value-negative";
}

function EmptyState({ children }: { children: ReactNode }) {
  return <div className="ps-empty-state">{children}</div>;
}

function PriorSensitivityTornado({ rows }: { rows: RoiTornadoRow[] }) {
  if (!rows.length) {
    return <EmptyState>Sensitivity tornado data is unavailable for this run.</EmptyState>;
  }

  const maxExtent = Math.max(
    ...rows.flatMap((row) => [Math.abs(Number(row.left ?? 0)), Math.abs(Number(row.right ?? 0)), Math.abs(Number(row.impact ?? 0))]),
    1
  );
  const scaleLabel = Math.ceil(maxExtent / 5) * 5;

  return (
    <div className="ps-tornado" role="img" aria-label="Self-response tornado chart ranked by prior sensitivity movement">
      <div className="ps-tornado-guidance" aria-hidden="true">
        <div className="ps-tornado-guidance__left">
          <strong>More conservative priors</strong>
          <span>(lower ROI)</span>
        </div>
        <div className="ps-tornado-guidance__right">
          <strong>More optimistic priors</strong>
          <span>(higher ROI)</span>
        </div>
      </div>
      {rows.map((row) => {
        const left = Number(row.left ?? 0);
        const right = Number(row.right ?? 0);
        const leftWidth = Math.min(50, (Math.abs(left) / maxExtent) * 50);
        const rightWidth = Math.min(50, (Math.abs(right) / maxExtent) * 50);
        return (
          <div className="ps-tornado-row" key={String(row.channel)}>
            <div className="ps-tornado-channel">{channelLabel(row.channel)}</div>
            <div className="ps-tornado-track">
              <span className="ps-tornado-axis" aria-hidden="true" />
              <span className="ps-tornado-bar ps-tornado-bar--lower" style={{ width: `${leftWidth}%` }} />
              <span className="ps-tornado-bar ps-tornado-bar--higher" style={{ width: `${rightWidth}%` }} />
            </div>
            <div className="ps-tornado-value">{formatPercent(row.impact, 1)}</div>
          </div>
        );
      })}
      <div className="ps-tornado-scale" aria-hidden="true">
        <span>-{formatPercent(scaleLabel, 0)}</span>
        <span>0%</span>
        <span>+{formatPercent(scaleLabel, 0)}</span>
      </div>
    </div>
  );
}

function SummaryCard({
  title,
  value,
  subtitle,
  footer,
  tone,
}: {
  title: string;
  value: string;
  subtitle: string;
  footer: string;
  tone: "blue" | "green" | "violet";
}) {
  return (
    <article className="ps-summary-card">
      <div className={`ps-summary-icon ps-summary-icon--${tone}`} aria-hidden="true" />
      <div>
        <h3>{title}</h3>
        <strong>{value}</strong>
        <span>{subtitle}</span>
        <p>{footer}</p>
      </div>
    </article>
  );
}

function buildCsv(rows: Array<Array<unknown>>) {
  return rows.map((row) => row.map(csvEscape).join(",")).join("\n");
}

function buildAuditType(payload: DashboardPayload) {
  const settings = payload.how_this_was_run?.settings || [];
  const badges = payload.how_this_was_run?.badges || [];
  const values = [...settings, ...badges].map((item) => `${item.label || ""} ${item.value || ""}`.trim());
  return values.find((value) => /grid|prior|audit|roi/i.test(value)) || payload.how_this_was_run?.summary || "Prior sensitivity audit";
}

function stabilityNote(payload: DashboardPayload) {
  const candidates = [...(payload.quick_overview_lines || []), ...(payload.recommendations || []), payload.decision_card?.score_note || ""];
  return candidates.find((line) => /threshold|stability|guardrail/i.test(line)) || "Stability threshold note unavailable for this run.";
}

export function PriorSensitivityPage() {
  const result = useCurrentResult();
  const { payload } = result;
  const tornadoRows = selectSelfResponseTornadoRows(payload);
  const dollarRows = selectDollarTornadoRows(payload);
  const rankingRows = [...(payload.rank_rows || [])].sort((a, b) => {
    const bValue = Math.abs(Number(b.primary_value ?? b.max_abs_pct_change ?? b.max_abs_delta_roi ?? 0));
    const aValue = Math.abs(Number(a.primary_value ?? a.max_abs_pct_change ?? a.max_abs_delta_roi ?? 0));
    return bValue - aValue;
  });
  const runScope = selectRunScope(payload);
  const targetChannelCount = payload.target_channel_detail?.options?.length ?? payload.overview?.n_channels ?? rankingRows.length;
  const defaultTarget = payload.target_channel_detail?.default_channel || payload.workbench?.default_channel;
  const gridSize = dollarRows[0]?.n ?? tornadoRows[0]?.n ?? payload.diagnostics_overview?.n_runs;
  const usesRevenueEquivalent = isFiniteNumber(payload.outcome_context?.revenue_per_kpi);
  const metricLabel = payload.outcome_context?.metric_label || payload.outcome_context?.kpi_type_effective || "ROI";

  const handleExport = () => {
    downloadText(
      `prior-sensitivity-${result.activeRunId || "run"}.json`,
      JSON.stringify(
        {
          run_id: result.activeRunId,
          metric_label: metricLabel,
          outcome_context: payload.outcome_context ?? null,
          target_channel_detail: payload.target_channel_detail ?? null,
          audit_scope: payload.how_this_was_run ?? null,
          roi_tornado_rows: tornadoRows,
          dollar_tornado_rows: dollarRows,
          rank_rows: rankingRows,
        },
        null,
        2
      ),
      "application/json"
    );
  };

  const handleExportCsv = () => {
    downloadText(
      `prior-sensitivity-ranking-${result.activeRunId || "run"}.csv`,
      buildCsv([
        ["Channel", "Prior Dist", "Baseline ROI", "Max Abs Movement"],
        ...rankingRows.map((row) => [row.channel, row.roi_prior_dist, row.baseline_roi, row.primary_value ?? row.max_abs_pct_change ?? row.max_abs_delta_roi]),
      ]),
      "text/csv"
    );
  };

  return (
    <SectionScaffold
      title="Results / Prior Sensitivity"
      summary="Read-only view of which channels moved most across the completed fixed ROI-prior grid."
      sourceLabel={result.sourceLabel}
      sourceDetail={result.sourceDetail}
      sourceKind={result.sourceKind}
      activeRunId={result.activeRunId}
      runSummary={result.runSummary}
      buildResultsPath={result.buildResultsPath}
      titleStatusChip="POST-RUN"
      headerAside={
        <div className="ps-export">
          <button className="ps-export-button" type="button" onClick={handleExport}>
            <span className="ps-export-button__icon" aria-hidden="true" />
            Export
            <span className="ps-export-button__chevron" aria-hidden="true" />
          </button>
          <button className="ps-export-menu-button" type="button" onClick={handleExportCsv} aria-label="Export ranking as CSV">
            CSV
          </button>
        </div>
      }
    >
      <div className="prior-sensitivity-page">
        <section className="content-panel ps-tornado-card">
          <div className="section-title-row">
            <div>
              <span className="eyebrow">Full-System Prior Response</span>
              <h3>Self-Response Tornado</h3>
            </div>
            <span className="subtle-chip">{formatNumber(rankingRows.length)} ranking rows</span>
          </div>
          <PriorSensitivityTornado rows={tornadoRows} />
        </section>

        <section className="ps-summary-grid" aria-label="Prior sensitivity summary">
          <SummaryCard
            title="Target Channels"
            value={formatNumber(targetChannelCount)}
            subtitle="Completed target set"
            footer={targetChannelCount ? `${formatNumber(targetChannelCount)} channels included in this prior sensitivity audit.` : "Target channel metadata is unavailable for this run."}
            tone="blue"
          />
          <SummaryCard
            title="Default Target"
            value={defaultTarget ? channelLabel(defaultTarget) : "Unavailable"}
            subtitle="Default target channel"
            footer={defaultTarget ? `Movements are shown for the selected run's default target context: ${channelLabel(defaultTarget)}.` : "Default target channel is unavailable in this payload."}
            tone="green"
          />
          <SummaryCard
            title="Audit Scope"
            value={runScope.value.toLowerCase().includes("fixed") ? "Fixed grid" : statusText(runScope.value)}
            subtitle={buildAuditType(payload)}
            footer={stabilityNote(payload)}
            tone="violet"
          />
        </section>

        <section className="ps-bottom-grid">
          <article className="content-panel ps-table-card">
            <h3>Top Dollar Sensitivity Rows</h3>
            {dollarRows.length ? (
              <>
                <div className="table-shell ps-table-shell">
                  <table>
                    <thead>
                      <tr>
                        <th>Channel</th>
                        <th>Max Abs Dollar Change</th>
                        <th>Median Dollar Change</th>
                        <th>N</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dollarRows.map((row: DollarTornadoRow) => (
                        <tr key={String(row.channel)}>
                          <td>{channelLabel(row.channel)}</td>
                          <td className={signedMoneyClass(row.max_abs_dollar_change)}>{formatMoneyCompact(row.max_abs_dollar_change)}</td>
                          <td className={signedMoneyClass(row.median_dollar_change)}>{formatMoneyCompact(row.median_dollar_change)}</td>
                          <td>{formatNumber(row.n)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {usesRevenueEquivalent ? <p className="ps-card-footer">Dollar changes are based on revenue-equivalent ROI. N = number of prior grid points.</p> : null}
              </>
            ) : (
              <EmptyState>Dollar sensitivity data is unavailable for this run.</EmptyState>
            )}
          </article>

          <article className="content-panel ps-table-card">
            <h3>Prior Sensitivity Ranking</h3>
            {rankingRows.length ? (
              <>
                <div className="table-shell ps-table-shell">
                  <table>
                    <thead>
                      <tr>
                        <th>Channel</th>
                        <th>Prior Dist</th>
                        <th>Baseline ROI</th>
                        <th>Max Abs Movement</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rankingRows.map((row: RankRow) => (
                        <tr key={`${row.channel}-${row.roi_prior_dist}-${row.baseline_roi}`}>
                          <td>{channelLabel(row.channel)}</td>
                          <td>{statusText(row.roi_prior_dist)}</td>
                          <td>{formatNumber(row.baseline_roi, 3)}</td>
                          <td>{formatMovementValue(row)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="ps-card-footer">Ranked by Max Abs Movement across the prior grid{gridSize ? ` (${formatNumber(gridSize)} grid points).` : "."}</p>
              </>
            ) : (
              <EmptyState>Prior sensitivity ranking data is unavailable for this run.</EmptyState>
            )}
          </article>

          <aside className="content-panel ps-interpretation-card">
            <div className="ps-interpretation-title">
              <span aria-hidden="true">i</span>
              <h3>Interpretation</h3>
            </div>
            <p>This page ranks channels by how much their {metricLabel} results moved across the ROI-prior grid.</p>
            <p>These rankings reflect sensitivity to prior assumptions, not business performance.</p>
            <p>Use this to identify channels requiring additional review before drawing stronger conclusions.</p>
          </aside>
        </section>
      </div>
    </SectionScaffold>
  );
}
