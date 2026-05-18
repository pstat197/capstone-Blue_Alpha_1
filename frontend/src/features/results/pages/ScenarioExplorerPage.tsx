import { Fragment, useEffect, useMemo, useState } from "react";
import { SectionScaffold } from "../components/SectionScaffold";
import { useCurrentResult } from "../data/resultLoader";
import { channelLabel, formatNumber } from "../data/resultSelectors";

type Row = Record<string, unknown>;

const NA = "NA";

function numeric(value: unknown): number | undefined {
  if (value === null || value === undefined || value === "") return undefined;
  const n = Number(value);
  return Number.isFinite(n) ? n : undefined;
}

function sameNumber(a: unknown, b: unknown): boolean {
  const an = numeric(a);
  const bn = numeric(b);
  return an !== undefined && bn !== undefined && Math.abs(an - bn) < 1e-9;
}

function uniqNumbers(values: unknown[] | undefined): number[] {
  return [...new Set((values || []).map(numeric).filter((value): value is number => value !== undefined))].sort((a, b) => a - b);
}

function metricLabel(value: unknown, digits = 3): string {
  const n = numeric(value);
  return n === undefined ? NA : formatNumber(n, digits);
}

function percentLabel(value: unknown, digits = 1): string {
  const n = numeric(value);
  return n === undefined ? NA : `${formatNumber(n, digits)}%`;
}

function shareLabel(value: unknown): string {
  const n = numeric(value);
  return n === undefined ? NA : `${formatNumber(n * 100, 1)}%`;
}

function compactValue(value: unknown): string {
  const n = numeric(value);
  if (n === undefined) return NA;
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(n);
}

function rowMu(row: Row): number | undefined {
  return numeric(row.roi_prior_mu ?? row.prior_roi_mu);
}

function rowSigma(row: Row): number | undefined {
  return numeric(row.roi_prior_sigma ?? row.prior_roi_sigma);
}

function rowContribution(row: Row | undefined): number | undefined {
  if (!row) return undefined;
  return numeric(row.effect_value ?? row.contribution_value);
}

function rowShare(row: Row | undefined): number | undefined {
  if (!row) return undefined;
  return numeric(row.effect_share ?? row.contribution_share);
}

function selectedMetric(row: Row | undefined): number | undefined {
  if (!row) return undefined;
  return numeric(row.estimated_roi ?? row.roi ?? rowContribution(row));
}

function getRowKey(channel: string, mu: number, sigma: number) {
  return `${channel}|${mu}|${sigma}`;
}

function MiniLineChart({
  xLabel,
  points,
  roiLegend,
}: {
  xLabel: string;
  points: Array<{ x: number; roi?: number; contribution?: number }>;
  roiLegend: string;
}) {
  const width = 420;
  const height = 210;
  const pad = { left: 44, right: 52, top: 28, bottom: 38 };
  const validRoi = points.filter((point) => point.roi !== undefined);
  const validContribution = points.filter((point) => point.contribution !== undefined);
  const xs = points.map((point) => point.x);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const roiMax = Math.max(1, ...validRoi.map((point) => point.roi || 0));
  const contributionMax = Math.max(1, ...validContribution.map((point) => point.contribution || 0));
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const scaleX = (x: number) => pad.left + (maxX === minX ? plotW / 2 : ((x - minX) / (maxX - minX)) * plotW);
  const scaleY = (value: number, max: number) => pad.top + plotH - (value / max) * plotH;
  const pathFor = (key: "roi" | "contribution", max: number) =>
    points
      .filter((point) => point[key] !== undefined)
      .map((point, index) => `${index === 0 ? "M" : "L"} ${scaleX(point.x)} ${scaleY(point[key] || 0, max)}`)
      .join(" ");

  if (!validRoi.length && !validContribution.length) {
    return <div className="scenario-empty-state">No ROI or contribution series is available for this slice.</div>;
  }

  return (
    <div className="scenario-line-chart">
      <div className="scenario-legend">
        {validRoi.length ? <span><i className="legend-dot legend-dot--roi" />{roiLegend}</span> : null}
        {validContribution.length ? <span><i className="legend-dot legend-dot--contribution" />Contribution</span> : null}
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${xLabel} marginal response chart`}>
        {[0, 0.25, 0.5, 0.75, 1].map((tick) => (
          <line key={tick} x1={pad.left} x2={width - pad.right} y1={pad.top + tick * plotH} y2={pad.top + tick * plotH} className="chart-grid-line" />
        ))}
        <text x={pad.left - 10} y={pad.top + 4} className="chart-axis-label" textAnchor="end">ROI</text>
        <text x={width - 2} y={pad.top + 4} className="chart-axis-label" textAnchor="end">Contribution</text>
        <line x1={pad.left} x2={width - pad.right} y1={height - pad.bottom} y2={height - pad.bottom} className="chart-axis-line" />
        <line x1={pad.left} x2={pad.left} y1={pad.top} y2={height - pad.bottom} className="chart-axis-line" />
        {validRoi.length ? <path d={pathFor("roi", roiMax)} className="chart-line chart-line--roi" /> : null}
        {validContribution.length ? <path d={pathFor("contribution", contributionMax)} className="chart-line chart-line--contribution" /> : null}
        {validRoi.map((point) => <circle key={`roi-${point.x}`} cx={scaleX(point.x)} cy={scaleY(point.roi || 0, roiMax)} r="4" className="chart-point chart-point--roi" />)}
        {validContribution.map((point) => <circle key={`contribution-${point.x}`} cx={scaleX(point.x)} cy={scaleY(point.contribution || 0, contributionMax)} r="4" className="chart-point chart-point--contribution" />)}
        {points.map((point) => (
          <text key={point.x} x={scaleX(point.x)} y={height - 14} className="chart-tick" textAnchor="middle">{formatNumber(point.x, 2).replace(/\.00$/, "")}</text>
        ))}
        <text x={pad.left + plotW / 2} y={height - 1} className="chart-axis-label" textAnchor="middle">{xLabel}</text>
      </svg>
    </div>
  );
}

export function ScenarioExplorerPage() {
  const result = useCurrentResult();
  const payload = result.payload;
  const workbench = payload.workbench;
  const rows = useMemo(() => (workbench?.run_rows || []) as Row[], [workbench?.run_rows]);
  const channels = useMemo(() => {
    const fromPayload = workbench?.available_channels || [];
    const fromRows = rows.map((row) => String(row.target_channel || row.channel || "")).filter(Boolean);
    return [...new Set([...fromPayload, ...fromRows])].sort();
  }, [rows, workbench?.available_channels]);
  const muValues = useMemo(() => uniqNumbers(workbench?.mu_values?.length ? workbench.mu_values : rows.map(rowMu)), [rows, workbench?.mu_values]);
  const sigmaValues = useMemo(() => uniqNumbers(workbench?.sigma_values?.length ? workbench.sigma_values : rows.map(rowSigma)), [rows, workbench?.sigma_values]);
  const baseline = workbench?.explicit_baseline as Row | undefined;
  const baselineMu = numeric(baseline?.mu);
  const baselineSigma = numeric(baseline?.sigma);
  const defaultChannel = workbench?.default_channel && channels.includes(workbench.default_channel) ? workbench.default_channel : channels[0] || "";
  const [channel, setChannel] = useState(defaultChannel);
  const [muIndex, setMuIndex] = useState(() => Math.max(0, muValues.findIndex((value) => sameNumber(value, baselineMu)) || 0));
  const [sigmaIndex, setSigmaIndex] = useState(() => Math.max(0, sigmaValues.findIndex((value) => sameNumber(value, baselineSigma)) || 0));

  useEffect(() => {
    if (!channels.includes(channel)) setChannel(defaultChannel);
  }, [channel, channels, defaultChannel]);

  const selectedMu = muValues[Math.min(muIndex, Math.max(muValues.length - 1, 0))] ?? 0;
  const selectedSigma = sigmaValues[Math.min(sigmaIndex, Math.max(sigmaValues.length - 1, 0))] ?? 0;
  const isBaselineMu = sameNumber(selectedMu, baselineMu);
  const isBaselineSigma = sameNumber(selectedSigma, baselineSigma);
  const isBaseline = isBaselineMu && isBaselineSigma;

  const scenarioRows = useMemo(() => {
    const targetRows = rows.filter((row) => String(row.target_channel || "") === channel && sameNumber(rowMu(row), selectedMu) && sameNumber(rowSigma(row), selectedSigma));
    if (targetRows.length) return targetRows;
    const runId = rows.find((row) => String(row.channel || "") === channel && sameNumber(rowMu(row), selectedMu) && sameNumber(rowSigma(row), selectedSigma))?.run_id;
    return rows.filter((row) => runId !== undefined && row.run_id === runId);
  }, [channel, rows, selectedMu, selectedSigma]);

  const selectedRow = useMemo(() => {
    return (
      scenarioRows.find((row) => String(row.channel || "") === channel) ||
      rows.find((row) => String(row.channel || "") === channel && sameNumber(rowMu(row), selectedMu) && sameNumber(rowSigma(row), selectedSigma))
    );
  }, [channel, rows, scenarioRows, selectedMu, selectedSigma]);

  const baselineRow = useMemo(() => {
    if (baselineMu === undefined || baselineSigma === undefined) return undefined;
    return rows.find((row) => String(row.target_channel || "") === channel && String(row.channel || "") === channel && sameNumber(rowMu(row), baselineMu) && sameNumber(rowSigma(row), baselineSigma));
  }, [baselineMu, baselineSigma, channel, rows]);

  const selectedRoi = selectedMetric(selectedRow);
  const baselineRoi = numeric(selectedRow?.baseline_roi) ?? selectedMetric(baselineRow);
  const deltaRoi = selectedRoi !== undefined && baselineRoi !== undefined ? selectedRoi - baselineRoi : undefined;
  const pctChange = numeric(selectedRow?.pct_change);
  const gridCombos = muValues.flatMap((mu) => sigmaValues.map((sigma) => ({ mu, sigma })));
  const gridPosition = gridCombos.findIndex((point) => sameNumber(point.mu, selectedMu) && sameNumber(point.sigma, selectedSigma)) + 1;
  const rowByPoint = useMemo(() => {
    const map = new Map<string, Row>();
    rows.forEach((row) => {
      if (String(row.target_channel || "") === channel && String(row.channel || "") === channel) {
        const mu = rowMu(row);
        const sigma = rowSigma(row);
        if (mu !== undefined && sigma !== undefined) map.set(getRowKey(channel, mu, sigma), row);
      }
    });
    return map;
  }, [channel, rows]);
  const heatValues = [...rowByPoint.values()].map(selectedMetric).filter((value): value is number => value !== undefined);
  const heatMin = Math.min(...heatValues);
  const heatMax = Math.max(...heatValues);
  const heatColor = (value: number | undefined) => {
    if (value === undefined || !Number.isFinite(heatMin) || !Number.isFinite(heatMax)) return undefined;
    const t = heatMax === heatMin ? 0.55 : (value - heatMin) / (heatMax - heatMin);
    return `rgba(30, 105, 220, ${0.12 + t * 0.72})`;
  };
  const muSeries = muValues.map((mu) => {
    const row = rowByPoint.get(getRowKey(channel, mu, selectedSigma));
    return { x: mu, roi: numeric(row?.estimated_roi), contribution: rowContribution(row) };
  });
  const sigmaSeries = sigmaValues.map((sigma) => {
    const row = rowByPoint.get(getRowKey(channel, selectedMu, sigma));
    return { x: sigma, roi: numeric(row?.estimated_roi), contribution: rowContribution(row) };
  });
  const allocationRows = scenarioRows
    .map((row) => {
      const spend = numeric(row.spend_share);
      const effect = rowShare(row);
      return { channel: String(row.channel || ""), spend, effect, gap: spend !== undefined && effect !== undefined ? effect - spend : undefined };
    })
    .filter((row) => row.channel)
    .sort((a, b) => Math.abs(b.gap ?? 0) - Math.abs(a.gap ?? 0));
  const allocationReady = allocationRows.length > 0 && allocationRows.every((row) => row.spend !== undefined && row.effect !== undefined && row.gap !== undefined);
  const largestGap = allocationRows.find((row) => row.gap !== undefined);
  const outcomeContext = payload.outcome_context;
  const contextText = outcomeContext?.revenue_per_kpi !== undefined
    ? `${outcomeContext.metric_label || "Revenue-equivalent ROI"} based on revenue_per_kpi = ${formatNumber(outcomeContext.revenue_per_kpi, 2).replace(/\.00$/, "")}`
    : `${outcomeContext?.metric_label || "ROI"} revenue handling unavailable`;

  return (
    <SectionScaffold
      title="Results / Scenario Explorer"
      summary="Interactively inspect how different prior assumptions affect selected channel outcomes."
      sourceLabel={result.sourceLabel}
      sourceDetail={result.sourceDetail}
      sourceKind={result.sourceKind}
      activeRunId={result.activeRunId}
      runSummary={result.runSummary}
      buildResultsPath={result.buildResultsPath}
      headerAside={<span className="scenario-header-context">{contextText}</span>}
    >
      <div className="scenario-explorer">
        {!rows.length || !muValues.length || !sigmaValues.length || !channels.length ? (
          <section className="content-panel scenario-empty-state">
            Scenario workbench data is unavailable for this run. Expected `workbench.run_rows`, channels, mu values, and sigma values in the selected result payload.
          </section>
        ) : (
          <>
            <section className="scenario-studio-card" aria-label="Prior Scenario Studio">
              <div className="scenario-control scenario-control--channel">
                <span className="scenario-card-kicker">Prior Scenario Studio</span>
                <label htmlFor="scenario-channel">Channel</label>
                <select id="scenario-channel" value={channel} onChange={(event) => setChannel(event.target.value)}>
                  {channels.map((item) => <option key={item} value={item}>{channelLabel(item)}</option>)}
                </select>
              </div>
              <div className="scenario-control">
                <div className="scenario-control-label">
                  <label htmlFor="scenario-mu">ROI Mu (selected scenario)</label>
                  <span className="help-dot" title="Prior ROI mean grid value.">?</span>
                  {isBaselineMu ? <span className="baseline-chip">Baseline</span> : null}
                </div>
                <input id="scenario-mu" type="range" min="0" max={Math.max(muValues.length - 1, 0)} step="1" value={muIndex} onChange={(event) => setMuIndex(Number(event.target.value))} />
                <div className="slider-ticks">{muValues.map((value) => <span key={value}>{formatNumber(value, 2).replace(/\.00$/, "")}</span>)}</div>
              </div>
              <div className="scenario-control">
                <div className="scenario-control-label">
                  <label htmlFor="scenario-sigma">ROI Sigma (selected scenario)</label>
                  <span className="help-dot" title="Prior ROI uncertainty grid value.">?</span>
                  {isBaselineSigma ? <span className="baseline-chip">Baseline</span> : null}
                </div>
                <input id="scenario-sigma" type="range" min="0" max={Math.max(sigmaValues.length - 1, 0)} step="1" value={sigmaIndex} onChange={(event) => setSigmaIndex(Number(event.target.value))} />
                <div className="slider-ticks">{sigmaValues.map((value) => <span key={value}>{formatNumber(value, 2).replace(/\.00$/, "")}</span>)}</div>
              </div>
            </section>

            <section className="scenario-metric-grid" aria-label="Selected scenario metrics">
              <article className="scenario-metric-card"><span>Selected Prior</span><strong>{metricLabel(selectedRoi)}</strong><p>{payload.outcome_context?.metric_label || "ROI"}</p></article>
              <article className="scenario-metric-card"><span>Baseline ROI</span><strong>{baselineRoi === undefined ? NA : metricLabel(baselineRoi)}</strong><p>{baselineRoi === undefined ? "Baseline unavailable" : payload.outcome_context?.metric_label || "ROI"}</p></article>
              <article className="scenario-metric-card"><span>Delta ROI</span><strong>{deltaRoi === undefined ? NA : `${deltaRoi >= 0 ? "+" : ""}${metricLabel(deltaRoi)}`}</strong><p>{baselineRoi === undefined ? "Baseline unavailable" : pctChange !== undefined ? `Change ${percentLabel(pctChange)}` : "Percent change unavailable"}</p></article>
              <article className="scenario-metric-card"><span>Contribution Share</span><strong>{shareLabel(rowShare(selectedRow))}</strong><p>{rowShare(selectedRow) === undefined ? "Contribution/effect share unavailable" : "Selected scenario"}</p></article>
              <article className="scenario-metric-card scenario-metric-card--split"><span>Prior Grid</span><strong>{gridPosition > 0 ? `${gridPosition} / ${gridCombos.length}` : NA}</strong><p>{isBaseline ? "Baseline" : "Non-baseline"} ROI Mu / ROI Sigma</p></article>
            </section>

            <section className="scenario-visual-grid" aria-label="Scenario visual comparison">
              <article className="scenario-chart-card">
                <h3>Selected Channel Mu x Sigma ROI Heatmap <span className="help-dot" title="Rows are sigma values; columns are mu values.">?</span></h3>
                <div className="heatmap-shell">
                  <span className="heatmap-axis heatmap-axis--y">Sigma</span>
                  <div className="heatmap-grid" style={{ gridTemplateColumns: `44px repeat(${muValues.length}, minmax(38px, 1fr))` }}>
                    <span />
                    {muValues.map((mu) => <b key={`mu-${mu}`}>{formatNumber(mu, 2).replace(/\.00$/, "")}</b>)}
                    {[...sigmaValues].reverse().map((sigma) => (
                      <Fragment key={`sigma-row-${sigma}`}>
                        <b key={`sigma-label-${sigma}`}>{formatNumber(sigma, 2).replace(/\.00$/, "")}</b>
                        {muValues.map((mu) => {
                          const value = selectedMetric(rowByPoint.get(getRowKey(channel, mu, sigma)));
                          const selected = sameNumber(mu, selectedMu) && sameNumber(sigma, selectedSigma);
                          return (
                            <span
                              key={`${mu}-${sigma}`}
                              className={selected ? "heatmap-cell heatmap-cell--selected" : value === undefined ? "heatmap-cell heatmap-cell--missing" : "heatmap-cell"}
                              style={{ backgroundColor: heatColor(value) }}
                            >
                              {value === undefined ? NA : metricLabel(value, 2)}
                            </span>
                          );
                        })}
                      </Fragment>
                    ))}
                  </div>
                  <span className="heatmap-axis heatmap-axis--x">Mu</span>
                </div>
              </article>
              <article className="scenario-chart-card">
                <h3>Mu Marginal Response (Selected Sigma) <span className="help-dot" title="Mu varies while sigma stays selected.">?</span></h3>
                <MiniLineChart xLabel="Mu" points={muSeries} roiLegend={`ROI (sigma=${formatNumber(selectedSigma, 2).replace(/\.00$/, "")})`} />
              </article>
              <article className="scenario-chart-card">
                <h3>Sigma Marginal Response (Selected Mu) <span className="help-dot" title="Sigma varies while mu stays selected.">?</span></h3>
                <MiniLineChart xLabel="Sigma" points={sigmaSeries} roiLegend={`ROI (mu=${formatNumber(selectedMu, 2).replace(/\.00$/, "")})`} />
              </article>
            </section>

            <section className="scenario-allocation-card">
              <div className="allocation-copy">
                <h3>Allocation Gap <span className="help-dot" title="Effect share minus spend share.">?</span></h3>
                <p>Dumbbell view by channel: effect share minus spend share.</p>
                {allocationReady && largestGap ? (
                  <div className="allocation-callout">
                    Largest allocation gap: {channelLabel(largestGap.channel)} (effect - spend = {largestGap.gap && largestGap.gap >= 0 ? "+" : ""}{formatNumber((largestGap.gap || 0) * 100, 3)} pp).
                  </div>
                ) : (
                  <div className="allocation-callout allocation-callout--missing">Spend share or contribution/effect share is missing for this selected scenario.</div>
                )}
                <div className="scenario-legend scenario-legend--left"><span><i className="legend-dot legend-dot--spend" />Spend</span><span><i className="legend-dot legend-dot--roi" />Effect</span></div>
              </div>
              <div className="dumbbell-chart">
                {allocationReady ? allocationRows.map((row) => {
                  const spend = row.spend || 0;
                  const effect = row.effect || 0;
                  const left = Math.min(spend, effect) * 100;
                  const width = Math.abs(effect - spend) * 100;
                  return (
                    <div className="dumbbell-row" key={row.channel}>
                      <strong>{channelLabel(row.channel)}</strong>
                      <div className="dumbbell-track">
                        <span className="dumbbell-line" style={{ left: `${left}%`, width: `${width}%` }} />
                        <span className="dumbbell-dot dumbbell-dot--spend" style={{ left: `${spend * 100}%` }} />
                        <span className="dumbbell-dot dumbbell-dot--effect" style={{ left: `${effect * 100}%` }} />
                      </div>
                      <span>{row.gap && row.gap >= 0 ? "+" : ""}{formatNumber((row.gap || 0) * 100, 3)} pp</span>
                    </div>
                  );
                }) : <div className="scenario-empty-state">Allocation gap chart unavailable for the selected scenario.</div>}
                {allocationReady ? <small>Channels shown: {allocationRows.length}. Values use selected scenario rows.</small> : null}
              </div>
            </section>
          </>
        )}
      </div>
    </SectionScaffold>
  );
}
