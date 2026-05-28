import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { SectionScaffold } from "../components/SectionScaffold";
import { ContextualHelpButton } from "../../../shared/ContextualHelp";
import { useCurrentResult } from "../data/resultLoader";
import { channelLabel, formatNumber } from "../data/resultSelectors";
import { ChannelLogo, displayChannelName } from "../../workflow/data/channelRegistry";

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

function ppLabel(value: unknown, digits = 1): string {
  const n = numeric(value);
  if (n === undefined) return NA;
  return `${n >= 0 ? "+" : ""}${formatNumber(n * 100, digits)} pp`;
}

function rowMu(row: Row): number | undefined {
  return numeric(row.roi_prior_mu ?? row.prior_roi_mu);
}

function rowSigma(row: Row): number | undefined {
  return numeric(row.roi_prior_sigma ?? row.prior_roi_sigma);
}

function rowDist(row: Row | undefined): string | undefined {
  if (!row) return undefined;
  const value = row.roi_prior_dist ?? row.prior_roi_dist;
  return value === null || value === undefined || value === "" ? undefined : String(value);
}

function rowContribution(row: Row | undefined): number | undefined {
  if (!row) return undefined;
  return numeric(row.effect_value ?? row.contribution_value);
}

function rowShare(row: Row | undefined): number | undefined {
  if (!row) return undefined;
  return numeric(row.effect_share ?? row.contribution_share);
}

function rowShareKind(row: Row | undefined): "effect" | "contribution" | undefined {
  if (!row) return undefined;
  if (numeric(row.effect_share) !== undefined) return "effect";
  if (numeric(row.contribution_share) !== undefined) return "contribution";
  return undefined;
}

function hasShare(row: Row | undefined): boolean {
  return rowShare(row) !== undefined;
}

function selectedMetric(row: Row | undefined): number | undefined {
  if (!row) return undefined;
  return numeric(row.estimated_roi ?? row.roi ?? rowContribution(row));
}

function getRowKey(channel: string, mu: number, sigma: number) {
  return `${channel}|${mu}|${sigma}`;
}

function getPointKey(mu: number, sigma: number) {
  return `${mu}|${sigma}`;
}

function indexOfNumber(values: number[], selected: number): number {
  const index = values.findIndex((value) => sameNumber(value, selected));
  return index >= 0 ? index : 0;
}

function sliderMarkerPosition(values: number[], marker: number | undefined): number | undefined {
  if (marker === undefined) return undefined;
  const index = values.findIndex((value) => sameNumber(value, marker));
  if (index < 0) return undefined;
  return values.length <= 1 ? 0 : (index / (values.length - 1)) * 100;
}

function baselineMarkerClass(position: number | undefined): string {
  if (position === undefined) return "scenario-baseline-marker";
  if (position <= 0) return "scenario-baseline-marker scenario-baseline-marker--start";
  if (position >= 100) return "scenario-baseline-marker scenario-baseline-marker--end";
  return "scenario-baseline-marker";
}

function buildAvailablePriorGridForChannel(rows: Row[], channel: string) {
  const pointMap = new Map<string, { mu: number; sigma: number; row: Row }>();
  const rowByPoint = new Map<string, Row>();

  rows.forEach((row) => {
    const targetChannel = String(row.target_channel || row.channel || "");
    const resultChannel = String(row.channel || "");
    if (targetChannel !== channel || resultChannel !== channel) return;

    const mu = rowMu(row);
    const sigma = rowSigma(row);
    if (mu === undefined || sigma === undefined) return;

    const pointKey = getPointKey(mu, sigma);
    if (!pointMap.has(pointKey)) {
      pointMap.set(pointKey, { mu, sigma, row });
    }
    rowByPoint.set(getRowKey(channel, mu, sigma), row);
  });

  const points = [...pointMap.values()].sort((a, b) => a.mu - b.mu || a.sigma - b.sigma);
  const muValues = uniqNumbers(points.map((point) => point.mu));
  const sigmaValues = uniqNumbers(points.map((point) => point.sigma));
  const hasPoint = (mu: number, sigma: number) => points.some((point) => sameNumber(point.mu, mu) && sameNumber(point.sigma, sigma));
  const sigmasForMu = (mu: number) => uniqNumbers(points.filter((point) => sameNumber(point.mu, mu)).map((point) => point.sigma));
  const musForSigma = (sigma: number) => uniqNumbers(points.filter((point) => sameNumber(point.sigma, sigma)).map((point) => point.mu));

  return { points, muValues, sigmaValues, rowByPoint, hasPoint, sigmasForMu, musForSigma };
}

function baselineMatchesRow(row: Row, mu: number | undefined, sigma: number | undefined, dist: string | undefined) {
  if (mu === undefined || sigma === undefined) return false;
  if (!sameNumber(rowMu(row), mu) || !sameNumber(rowSigma(row), sigma)) return false;
  return !dist || rowDist(row) === dist;
}

function allocationFromScenarioRow(row: Row) {
  const spend = numeric(row.spend_share);
  const effect = rowShare(row);
  const shareKind = rowShareKind(row);
  return {
    channel: String(row.channel || ""),
    spend,
    effect,
    shareKind,
    gap: spend !== undefined && effect !== undefined ? effect - spend : undefined,
    missingFields: [
      spend === undefined ? "spend_share" : "",
      effect === undefined ? "effect_share/contribution_share" : "",
    ].filter(Boolean),
  };
}

function allocationFromSpendEffectRow(row: Row) {
  const spendPct = numeric(row.spend_share_pct);
  const effectPct = numeric(row.effect_share_pct ?? row.contribution_share_pct);
  const gapPp = numeric(row.share_gap_pp);
  const spend = spendPct === undefined ? undefined : spendPct / 100;
  const effect = effectPct === undefined ? undefined : effectPct / 100;
  const gap = gapPp !== undefined ? gapPp / 100 : spend !== undefined && effect !== undefined ? effect - spend : undefined;
  return {
    channel: String(row.channel || ""),
    spend,
    effect,
    shareKind: numeric(row.effect_share_pct) !== undefined ? "effect" as const : "contribution" as const,
    gap,
    missingFields: [
      spend === undefined ? "spend_share_pct" : "",
      effect === undefined ? "effect_share_pct/contribution_share_pct" : "",
    ].filter(Boolean),
  };
}

function MiniLineChart({
  xLabel,
  points,
  roiLegend,
  secondaryLegend,
  secondaryAxisLabel,
  selectedX,
}: {
  xLabel: string;
  points: Array<{ x: number; roi?: number; secondary?: number }>;
  roiLegend: string;
  secondaryLegend: string;
  secondaryAxisLabel: string;
  selectedX: number;
}) {
  const width = 420;
  const height = 210;
  const pad = { left: 44, right: 52, top: 28, bottom: 38 };
  const validRoi = points.filter((point) => point.roi !== undefined);
  const validSecondary = points.filter((point) => point.secondary !== undefined);
  const xs = points.map((point) => point.x);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const roiMax = Math.max(1, ...validRoi.map((point) => point.roi || 0));
  const secondaryMax = Math.max(1, ...validSecondary.map((point) => point.secondary || 0));
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const scaleX = (x: number) => pad.left + (maxX === minX ? plotW / 2 : ((x - minX) / (maxX - minX)) * plotW);
  const scaleY = (value: number, max: number) => pad.top + plotH - (value / max) * plotH;
  const pathFor = (key: "roi" | "secondary", max: number) =>
    points
      .filter((point) => point[key] !== undefined)
      .map((point, index) => `${index === 0 ? "M" : "L"} ${scaleX(point.x)} ${scaleY(point[key] || 0, max)}`)
      .join(" ");

  if (!validRoi.length && !validSecondary.length) {
    return <div className="scenario-empty-state">No ROI or contribution series is available for this slice.</div>;
  }

  return (
    <div className="scenario-line-chart">
      <div className="scenario-legend">
        {validRoi.length ? <span><i className="legend-dot legend-dot--roi" />{roiLegend}</span> : null}
        {validSecondary.length ? <span><i className="legend-dot legend-dot--contribution" />{secondaryLegend}</span> : null}
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${xLabel} marginal response chart`}>
        {[0, 0.25, 0.5, 0.75, 1].map((tick) => (
          <line key={tick} x1={pad.left} x2={width - pad.right} y1={pad.top + tick * plotH} y2={pad.top + tick * plotH} className="chart-grid-line" />
        ))}
        <text x={pad.left - 10} y={pad.top + 4} className="chart-axis-label" textAnchor="end">ROI</text>
        <text x={width - 2} y={pad.top + 4} className="chart-axis-label" textAnchor="end">{secondaryAxisLabel}</text>
        <line x1={pad.left} x2={width - pad.right} y1={height - pad.bottom} y2={height - pad.bottom} className="chart-axis-line" />
        <line x1={pad.left} x2={pad.left} y1={pad.top} y2={height - pad.bottom} className="chart-axis-line" />
        {validRoi.length ? <path d={pathFor("roi", roiMax)} className="chart-line chart-line--roi" /> : null}
        {validSecondary.length ? <path d={pathFor("secondary", secondaryMax)} className="chart-line chart-line--contribution" /> : null}
        {validRoi.map((point) => (
          <circle key={`roi-${point.x}`} cx={scaleX(point.x)} cy={scaleY(point.roi || 0, roiMax)} r={sameNumber(point.x, selectedX) ? "6" : "4"} className={sameNumber(point.x, selectedX) ? "chart-point chart-point--roi chart-point--selected" : "chart-point chart-point--roi"}>
            <title>{`${xLabel} ${point.x}: ROI ${metricLabel(point.roi)}`}</title>
          </circle>
        ))}
        {validSecondary.map((point) => (
          <circle key={`secondary-${point.x}`} cx={scaleX(point.x)} cy={scaleY(point.secondary || 0, secondaryMax)} r={sameNumber(point.x, selectedX) ? "6" : "4"} className={sameNumber(point.x, selectedX) ? "chart-point chart-point--contribution chart-point--selected" : "chart-point chart-point--contribution"}>
            <title>{`${xLabel} ${point.x}: ${secondaryLegend} ${metricLabel(point.secondary)}`}</title>
          </circle>
        ))}
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
    const testedChannels = rows
      .filter((row) => {
        const targetChannel = String(row.target_channel || row.channel || "");
        const resultChannel = String(row.channel || "");
        return targetChannel && targetChannel === resultChannel && rowMu(row) !== undefined && rowSigma(row) !== undefined;
      })
      .map((row) => String(row.channel || ""));
    return [...new Set(testedChannels)].sort();
  }, [rows]);
  const payloadBaselinePrior = (payload.baseline_prior || workbench?.baseline_prior || workbench?.explicit_baseline) as Row | undefined;
  const explicitBaselineMu = numeric(payloadBaselinePrior?.roi_mu ?? payloadBaselinePrior?.mu);
  const explicitBaselineSigma = numeric(payloadBaselinePrior?.roi_sigma ?? payloadBaselinePrior?.sigma);
  const explicitBaselineDist = rowDist({
    roi_prior_dist: payloadBaselinePrior?.roi_dist ?? payloadBaselinePrior?.dist ?? payloadBaselinePrior?.distribution,
  });
  const hasExplicitBaseline = explicitBaselineMu !== undefined && explicitBaselineSigma !== undefined;
  const defaultChannel = workbench?.default_channel && channels.includes(workbench.default_channel) ? workbench.default_channel : channels[0] || "";
  const [channel, setChannel] = useState(defaultChannel);
  const [selectedPair, setSelectedPair] = useState<{ mu?: number; sigma?: number }>({});
  const [selectorOpen, setSelectorOpen] = useState(false);
  const selectorRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!channels.includes(channel)) setChannel(defaultChannel);
  }, [channel, channels, defaultChannel]);

  useEffect(() => {
    if (!selectorOpen) return;
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!selectorRef.current?.contains(event.target as Node)) {
        setSelectorOpen(false);
      }
    };
    document.addEventListener("mousedown", closeOnOutsideClick);
    return () => document.removeEventListener("mousedown", closeOnOutsideClick);
  }, [selectorOpen]);

  const channelGrid = useMemo(() => buildAvailablePriorGridForChannel(rows, channel), [channel, rows]);
  const channelBaselineRow = useMemo(() => {
    return rows.find((row) => {
      const isBaselineRow = String(row.is_baseline || "").toLowerCase() === "true";
      return isBaselineRow && String(row.target_channel || "") === channel && String(row.channel || "") === channel;
    });
  }, [channel, rows]);
  const baselineMu = hasExplicitBaseline ? explicitBaselineMu : channelBaselineRow ? rowMu(channelBaselineRow) : undefined;
  const baselineSigma = hasExplicitBaseline ? explicitBaselineSigma : channelBaselineRow ? rowSigma(channelBaselineRow) : undefined;
  const baselineDist = hasExplicitBaseline ? explicitBaselineDist : rowDist(channelBaselineRow);
  const baselineGridPoint = channelGrid.points.find((point) => baselineMatchesRow(point.row, baselineMu, baselineSigma, baselineDist));
  const fallbackPoint = baselineGridPoint ?? channelGrid.points[0];
  const rawSelectedMu = selectedPair.mu ?? fallbackPoint?.mu ?? 0;
  const rawSelectedSigma = selectedPair.sigma ?? fallbackPoint?.sigma ?? 0;
  const selectedPairIsValid = channelGrid.hasPoint(rawSelectedMu, rawSelectedSigma);
  const selectedMu = selectedPairIsValid ? rawSelectedMu : fallbackPoint?.mu ?? rawSelectedMu;
  const selectedSigma = selectedPairIsValid ? rawSelectedSigma : fallbackPoint?.sigma ?? rawSelectedSigma;
  const muSliderValues = channelGrid.musForSigma(selectedSigma);
  const sigmaSliderValues = channelGrid.sigmasForMu(selectedMu);
  const muIndex = indexOfNumber(muSliderValues, selectedMu);
  const sigmaIndex = indexOfNumber(sigmaSliderValues, selectedSigma);
  const baselineMuPosition = sliderMarkerPosition(muSliderValues, baselineMu);
  const baselineSigmaPosition = sliderMarkerPosition(sigmaSliderValues, baselineSigma);

  useEffect(() => {
    if (!channelGrid.points.length) return;
    if (sameNumber(selectedPair.mu, selectedMu) && sameNumber(selectedPair.sigma, selectedSigma)) return;
    setSelectedPair({ mu: selectedMu, sigma: selectedSigma });
  }, [channelGrid.points.length, selectedMu, selectedPair.mu, selectedPair.sigma, selectedSigma]);

  const handleMuChange = (index: number) => {
    const nextMu = muSliderValues[index] ?? selectedMu;
    const validSigmas = channelGrid.sigmasForMu(nextMu);
    const retainedSigma = validSigmas.find((sigma) => sameNumber(sigma, selectedSigma));
    setSelectedPair({ mu: nextMu, sigma: retainedSigma ?? validSigmas[0] ?? selectedSigma });
  };

  const handleSigmaChange = (index: number) => {
    const nextSigma = sigmaSliderValues[index] ?? selectedSigma;
    const validMus = channelGrid.musForSigma(nextSigma);
    const retainedMu = validMus.find((mu) => sameNumber(mu, selectedMu));
    setSelectedPair({ mu: retainedMu ?? validMus[0] ?? selectedMu, sigma: nextSigma });
  };

  const isBaselineMu = sameNumber(selectedMu, baselineMu);
  const isBaselineSigma = sameNumber(selectedSigma, baselineSigma);

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

  const isBaseline = isBaselineMu && isBaselineSigma && (!baselineDist || rowDist(selectedRow) === baselineDist);

  const baselineRow = useMemo(() => {
    if (baselineMu === undefined || baselineSigma === undefined) return undefined;
    const explicitMatch = rows.find((row) => {
      return String(row.target_channel || "") === channel && String(row.channel || "") === channel && baselineMatchesRow(row, baselineMu, baselineSigma, baselineDist);
    });
    return explicitMatch || (!hasExplicitBaseline ? channelBaselineRow : undefined);
  }, [baselineDist, baselineMu, baselineSigma, channel, channelBaselineRow, hasExplicitBaseline, rows]);

  const selectedRoi = selectedMetric(selectedRow);
  const baselineRoi = selectedMetric(baselineRow) ?? (!hasExplicitBaseline ? numeric(selectedRow?.baseline_roi) : undefined);
  const deltaRoi = selectedRoi !== undefined && baselineRoi !== undefined ? selectedRoi - baselineRoi : undefined;
  const pctChange = numeric(selectedRow?.pct_change);
  const gridPosition = channelGrid.points.findIndex((point) => sameNumber(point.mu, selectedMu) && sameNumber(point.sigma, selectedSigma)) + 1;
  const rowByPoint = channelGrid.rowByPoint;
  const heatValues = [...rowByPoint.values()].map(selectedMetric).filter((value): value is number => value !== undefined);
  const heatMin = Math.min(...heatValues);
  const heatMax = Math.max(...heatValues);
  const heatColor = (value: number | undefined) => {
    if (value === undefined || !Number.isFinite(heatMin) || !Number.isFinite(heatMax)) return undefined;
    const t = heatMax === heatMin ? 0.55 : (value - heatMin) / (heatMax - heatMin);
    return `rgba(30, 105, 220, ${0.12 + t * 0.72})`;
  };
  const shareKinds = [...rowByPoint.values()].map(rowShareKind).filter(Boolean);
  const useShareSeries = shareKinds.length > 0;
  const secondaryLegend = useShareSeries
    ? shareKinds.includes("effect") ? "Effect Share" : "Contribution Share"
    : "Contribution Value";
  const secondaryAxisLabel = useShareSeries ? "Share" : "Contribution Value";
  const secondaryValue = (row: Row | undefined) => useShareSeries ? rowShare(row) : rowContribution(row);
  const muSeries = muSliderValues.map((mu) => {
    const row = rowByPoint.get(getRowKey(channel, mu, selectedSigma));
    return { x: mu, roi: numeric(row?.estimated_roi), secondary: secondaryValue(row) };
  });
  const sigmaSeries = sigmaSliderValues.map((sigma) => {
    const row = rowByPoint.get(getRowKey(channel, selectedMu, sigma));
    return { x: sigma, roi: numeric(row?.estimated_roi), secondary: secondaryValue(row) };
  });
  const selectedScenarioAllocationRows = scenarioRows
    .map(allocationFromScenarioRow)
    .filter((row) => row.channel)
    .sort((a, b) => Math.abs(b.gap ?? 0) - Math.abs(a.gap ?? 0));
  const selectedScenarioAllocationReady =
    selectedScenarioAllocationRows.length > 0 &&
    selectedScenarioAllocationRows.every((row) => row.spend !== undefined && row.effect !== undefined && row.gap !== undefined);
  const runPayloadAllocationRows = ((payload.spend_effect_rows || []) as Row[])
    .map(allocationFromSpendEffectRow)
    .filter((row) => row.channel)
    .sort((a, b) => Math.abs(b.gap ?? 0) - Math.abs(a.gap ?? 0));
  const runPayloadAllocationReady =
    runPayloadAllocationRows.length > 0 &&
    runPayloadAllocationRows.every((row) => row.spend !== undefined && row.effect !== undefined && row.gap !== undefined);
  const allocationRows = selectedScenarioAllocationReady ? selectedScenarioAllocationRows : runPayloadAllocationRows;
  const allocationReady = selectedScenarioAllocationReady || runPayloadAllocationReady;
  const allocationSourceLabel = selectedScenarioAllocationReady ? "selected scenario rows" : "run-level spend/effect summary";
  const allocationShareLabel = allocationRows.some((row) => row.shareKind === "effect") ? "Effect" : "Contribution";
  const missingAllocationFields = [...new Set(selectedScenarioAllocationRows.flatMap((row) => row.missingFields))];
  const largestGap = allocationRows.find((row) => row.gap !== undefined);
  const allocationTicks = [0, 20, 40, 60, 80, 100];
  const outcomeContext = payload.outcome_context;
  const contextText = outcomeContext?.revenue_per_kpi !== undefined
    ? `${outcomeContext.metric_label || "Revenue-equivalent ROI"} based on revenue_per_kpi = ${formatNumber(outcomeContext.revenue_per_kpi, 2).replace(/\.00$/, "")}`
    : `${outcomeContext?.metric_label || "ROI"} revenue handling unavailable`;

  return (
    <SectionScaffold
      title="Scenario Explorer"
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
        {!rows.length || !channelGrid.muValues.length || !channelGrid.sigmaValues.length || !channels.length ? (
          <section className="content-panel scenario-empty-state">
            Scenario workbench data is unavailable for this run. Expected `workbench.run_rows` with tested channel-level ROI Mu and ROI Sigma values for at least one channel in the selected result payload.
          </section>
        ) : (
          <>
            <section className="scenario-studio-card" aria-label="Prior Scenario Studio">
              <div className="scenario-control scenario-control--channel">
                <span className="scenario-card-kicker">Prior Scenario Studio</span>
                <label htmlFor="scenario-channel">Channel</label>
                <div className="scenario-channel-select" ref={selectorRef}>
                  <button
                    id="scenario-channel"
                    className="scenario-channel-select-button"
                    type="button"
                    aria-haspopup="listbox"
                    aria-expanded={selectorOpen}
                    onClick={() => setSelectorOpen((open) => !open)}
                  >
                    <ChannelLogo channel={channel} />
                    <strong>{displayChannelName(channel).toUpperCase()}</strong>
                    <span className="ps-target-select-chevron" aria-hidden="true" />
                  </button>
                  {selectorOpen ? (
                    <div className="scenario-channel-select-menu" role="listbox" aria-label="Select channel">
                      {channels.map((item) => (
                        <button
                          className={item === channel ? "scenario-channel-select-option active" : "scenario-channel-select-option"}
                          type="button"
                          role="option"
                          aria-selected={item === channel}
                          value={item}
                          key={item}
                          onClick={() => {
                            setChannel(item);
                            setSelectorOpen(false);
                          }}
                        >
                          <ChannelLogo channel={item} />
                          <span>{displayChannelName(item).toUpperCase()}</span>
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
              <div className="scenario-control">
                <div className="scenario-control-label">
                  <label htmlFor="scenario-mu">ROI Mu (selected scenario)</label>
                </div>
                <div className="scenario-slider-shell">
                  <input id="scenario-mu" type="range" min="0" max={Math.max(muSliderValues.length - 1, 0)} step="1" value={muIndex} onChange={(event) => handleMuChange(Number(event.target.value))} />
                  {baselineMuPosition !== undefined ? (
                    <span className={baselineMarkerClass(baselineMuPosition)} style={{ left: `${baselineMuPosition}%` }}>
                      <i aria-hidden="true" />
                      <b>Baseline</b>
                    </span>
                  ) : null}
                </div>
                <div className="slider-ticks">{muSliderValues.map((value) => <span key={value}>{formatNumber(value, 2).replace(/\.00$/, "")}</span>)}</div>
              </div>
              <div className="scenario-control">
                <div className="scenario-control-label">
                  <label htmlFor="scenario-sigma">ROI Sigma (selected scenario)</label>
                </div>
                <div className="scenario-slider-shell">
                  <input id="scenario-sigma" type="range" min="0" max={Math.max(sigmaSliderValues.length - 1, 0)} step="1" value={sigmaIndex} onChange={(event) => handleSigmaChange(Number(event.target.value))} />
                  {baselineSigmaPosition !== undefined ? (
                    <span className={baselineMarkerClass(baselineSigmaPosition)} style={{ left: `${baselineSigmaPosition}%` }}>
                      <i aria-hidden="true" />
                      <b>Baseline</b>
                    </span>
                  ) : null}
                </div>
                <div className="slider-ticks">{sigmaSliderValues.map((value) => <span key={value}>{formatNumber(value, 2).replace(/\.00$/, "")}</span>)}</div>
              </div>
            </section>

            <section className="scenario-metric-grid" aria-label="Selected scenario metrics">
              <article className="scenario-metric-card"><span>Selected Prior</span><strong>{metricLabel(selectedRoi)}</strong><p>{payload.outcome_context?.metric_label || "ROI"}</p></article>
              <article className="scenario-metric-card"><span>Baseline ROI</span><strong>{baselineRoi === undefined ? NA : metricLabel(baselineRoi)}</strong><p>{baselineRoi === undefined ? "Baseline unavailable" : payload.outcome_context?.metric_label || "ROI"}</p></article>
              <article className="scenario-metric-card"><span>Delta ROI</span><strong>{deltaRoi === undefined ? NA : `${deltaRoi >= 0 ? "+" : ""}${metricLabel(deltaRoi)}`}</strong><p>{baselineRoi === undefined ? "Baseline unavailable" : pctChange !== undefined ? `Change ${percentLabel(pctChange)}` : "Percent change unavailable"}</p></article>
              <article className="scenario-metric-card"><span>Contribution Share</span><strong>{shareLabel(rowShare(selectedRow))}</strong><p>{rowShare(selectedRow) === undefined ? "Contribution/effect share unavailable" : "Selected scenario"}</p></article>
              <article className="scenario-metric-card scenario-metric-card--split"><span>Prior Grid</span><strong>{gridPosition > 0 ? `${gridPosition} / ${channelGrid.points.length}` : NA}</strong><p>{isBaseline ? "Baseline" : "Non-baseline"} ROI Mu / ROI Sigma</p></article>
            </section>

            <section className="scenario-visual-grid" aria-label="Scenario visual comparison">
              <article className="scenario-chart-card">
                <h3>
                  Selected Channel Mu x Sigma ROI Heatmap
                  <ContextualHelpButton sectionId="scenario-roi-heatmap" label="Explain ROI heatmap" />
                </h3>
                <div className="heatmap-shell">
                  <span className="heatmap-axis heatmap-axis--y">Sigma</span>
                  <div className="heatmap-grid" style={{ gridTemplateColumns: `44px repeat(${channelGrid.muValues.length}, minmax(38px, 1fr))` }}>
                    <span />
                    {channelGrid.muValues.map((mu) => <b key={`mu-${mu}`}>{formatNumber(mu, 2).replace(/\.00$/, "")}</b>)}
                    {[...channelGrid.sigmaValues].reverse().map((sigma) => (
                      <Fragment key={`sigma-row-${sigma}`}>
                        <b key={`sigma-label-${sigma}`}>{formatNumber(sigma, 2).replace(/\.00$/, "")}</b>
                        {channelGrid.muValues.map((mu) => {
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
                <h3>
                  Mu Marginal Response (Selected Sigma)
                  <ContextualHelpButton sectionId="scenario-mu-response" label="Explain Mu marginal response" />
                </h3>
                <MiniLineChart
                  xLabel="Mu"
                  points={muSeries}
                  roiLegend={`ROI (sigma=${formatNumber(selectedSigma, 2).replace(/\.00$/, "")})`}
                  secondaryLegend={secondaryLegend}
                  secondaryAxisLabel={secondaryAxisLabel}
                  selectedX={selectedMu}
                />
              </article>
              <article className="scenario-chart-card">
                <h3>
                  Sigma Marginal Response (Selected Mu)
                  <ContextualHelpButton sectionId="scenario-sigma-response" label="Explain Sigma marginal response" />
                </h3>
                <MiniLineChart
                  xLabel="Sigma"
                  points={sigmaSeries}
                  roiLegend={`ROI (mu=${formatNumber(selectedMu, 2).replace(/\.00$/, "")})`}
                  secondaryLegend={secondaryLegend}
                  secondaryAxisLabel={secondaryAxisLabel}
                  selectedX={selectedSigma}
                />
              </article>
            </section>

            <section className="scenario-allocation-card">
              <div className="allocation-copy">
                <h3>
                  Allocation Gap
                  <ContextualHelpButton sectionId="scenario-allocation-gap" label="Explain allocation gap" />
                </h3>
                <p>Dumbbell view by channel: {allocationShareLabel.toLowerCase()} share minus spend share.</p>
                {allocationReady && largestGap ? (
                  <div className="allocation-callout">
                    Largest allocation gap: {channelLabel(largestGap.channel)} ({allocationShareLabel.toLowerCase()} - spend = {ppLabel(largestGap.gap, 3)}).
                  </div>
                ) : (
                  <div className="allocation-callout allocation-callout--missing">
                    Spend share or contribution/effect share is missing for this selected scenario.
                    {missingAllocationFields.length ? ` Missing fields: ${missingAllocationFields.join(", ")}.` : ""}
                  </div>
                )}
                {allocationReady && !selectedScenarioAllocationReady ? (
                  <p className="allocation-source-note">Selected scenario rows do not include allocation shares; showing {allocationSourceLabel} from the same result payload.</p>
                ) : null}
                <div className="scenario-legend scenario-legend--left"><span><i className="legend-dot legend-dot--spend" />Spend</span><span><i className="legend-dot legend-dot--roi" />{allocationShareLabel}</span></div>
                {allocationReady ? <p className="allocation-footer-note">Axis interval: [0.0%, 100.0%]. Channels shown: {allocationRows.length}.</p> : null}
              </div>
              <div className="dumbbell-chart">
                {allocationReady ? (
                  <div className="dumbbell-row-group">
                    {allocationRows.map((row) => {
                      const spend = row.spend || 0;
                      const effect = row.effect || 0;
                      const left = Math.min(spend, effect) * 100;
                      const width = Math.abs(effect - spend) * 100;
                      const gap = row.gap || 0;
                      const labelLeft = Math.min(93, Math.max(7, Math.max(spend, effect) * 100 + 3));
                      const tooltip = `Spend: ${shareLabel(spend)}; ${allocationShareLabel}: ${shareLabel(effect)}; Gap: ${ppLabel(gap, 3)}`;
                      return (
                        <div className="dumbbell-row" key={row.channel} title={tooltip} aria-label={`${channelLabel(row.channel)} allocation gap. ${tooltip}`}>
                          <strong>{channelLabel(row.channel)}</strong>
                          <div className="dumbbell-track">
                            {allocationTicks.map((tick) => <span key={tick} className="dumbbell-grid-line" style={{ left: `${tick}%` }} />)}
                            <span className="dumbbell-axis-zero" aria-hidden="true" />
                            <span className={gap >= 0 ? "dumbbell-line dumbbell-line--positive" : "dumbbell-line dumbbell-line--negative"} style={{ left: `${left}%`, width: `${width}%` }} />
                            <span className="dumbbell-dot dumbbell-dot--spend" style={{ left: `${spend * 100}%` }} />
                            <span className="dumbbell-dot dumbbell-dot--effect" style={{ left: `${effect * 100}%` }} />
                            <span className={gap >= 0 ? "dumbbell-gap-inline dumbbell-gap-inline--positive" : "dumbbell-gap-inline dumbbell-gap-inline--negative"} style={{ left: `${labelLeft}%` }}>{ppLabel(gap, 3)}</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : <div className="scenario-empty-state">Allocation gap chart unavailable for the selected scenario. Missing fields: {missingAllocationFields.length ? missingAllocationFields.join(", ") : "spend/effect/contribution share fields"}.</div>}
                {allocationReady ? (
                  <div className="dumbbell-axis" aria-hidden="true">
                    <span />
                    <div>{allocationTicks.map((tick) => <span key={tick} style={{ left: `${tick}%` }}>{tick}%</span>)}</div>
                  </div>
                ) : null}
                {allocationReady ? <small>Values use {allocationSourceLabel}.</small> : null}
              </div>
            </section>
          </>
        )}
      </div>
    </SectionScaffold>
  );
}
