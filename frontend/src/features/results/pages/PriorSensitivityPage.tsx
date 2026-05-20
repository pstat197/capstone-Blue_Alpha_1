import { useEffect, useMemo, useRef, useState } from "react";
import { SectionScaffold } from "../components/SectionScaffold";
import { useCurrentResult } from "../data/resultLoader";
import type { SystemImpactRow, TargetChannelSummary, TargetRobustness } from "../data/resultTypes";
import { channelLabel, formatNumber, formatPercent } from "../data/resultSelectors";
import { ChannelLogo } from "../../workflow/data/channelRegistry";

type MetricMode = "pct" | "delta";

type MovementRow = {
  channel: string;
  isSelf: boolean;
  baselineRoi: number | null;
  medianPct: number | null;
  maxAbsPct: number | null;
  medianDeltaRoi: number | null;
  maxAbsDeltaRoi: number | null;
  leftPct: number | null;
  rightPct: number | null;
  leftDeltaRoi: number | null;
  rightDeltaRoi: number | null;
  n: number;
  stablePct: boolean;
};

const missing = "Unavailable";
const robustnessWeights = {
  prior: 0.6,
  data: 0.25,
  cross: 0.15,
};

function asNumber(value: unknown): number | null {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function median(values: Array<number | null | undefined>): number | null {
  const numeric = values.filter((value): value is number => Number.isFinite(value));
  if (!numeric.length) return null;
  const sorted = [...numeric].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function absMax(values: Array<number | null | undefined>): number | null {
  const numeric = values.filter((value): value is number => Number.isFinite(value));
  if (!numeric.length) return null;
  return Math.max(...numeric.map((value) => Math.abs(value)));
}

function signedClass(value: number | null): string {
  if (value === null || !Number.isFinite(value) || value === 0) return "";
  return value > 0 ? "ps-value-positive" : "ps-value-negative";
}

function signedPercent(value: number | null, digits = 1): string {
  if (value === null || !Number.isFinite(value)) return "NA";
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${formatPercent(value, digits)}`;
}

function signedNumber(value: number | null, digits = 3): string {
  if (value === null || !Number.isFinite(value)) return "NA";
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${formatNumber(value, digits)}`;
}

function scoreText(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "NA";
  return `${formatNumber(value, 0)} / 100`;
}

function bandClass(band: unknown): string {
  const key = String(band || "").toLowerCase();
  if (key.includes("high")) return "ps-band--high";
  if (key.includes("medium")) return "ps-band--medium";
  if (key.includes("low")) return "ps-band--low";
  return "ps-band--unknown";
}

function bandInterpretation(band: unknown): string {
  const key = String(band || "").toLowerCase();
  if (key.includes("low")) {
    return "Low robustness means this target channel's results are sensitive to prior assumptions. Additional review is recommended before drawing strong conclusions.";
  }
  if (key.includes("medium")) {
    return "Medium robustness means the result is usable directionally, but still needs caution where sensitivity or cross-channel effects are elevated.";
  }
  if (key.includes("high")) {
    return "High robustness means this target channel's results are relatively stable across tested prior assumptions.";
  }
  return "Band interpretation is unavailable for this run.";
}

function absoluteBandForScore(score: number | null): string {
  if (score === null || !Number.isFinite(score)) return "";
  if (score >= 75) return "High";
  if (score >= 50) return "Medium";
  return "Low";
}

function scoreField(row: Record<string, unknown> | undefined, keys: string[]): number | null {
  return asNumber(getField(row, keys));
}

function rawPayloadRobustnessScore(robustness?: TargetRobustness): number | null {
  return (
    asNumber(robustness?.channel_robustness_score) ??
    asNumber(robustness?.overall_channel_robustness_score) ??
    asNumber(robustness?.score) ??
    scoreField(robustness?.source_row, ["channel_robustness_score", "overall_channel_robustness_score"])
  );
}

function computedRobustnessScore(subscores: Array<{ id?: string; label?: string; value?: number | null }>): number | null {
  const byId = new Map(subscores.map((item) => [String(item.id || "").toLowerCase(), asNumber(item.value)]));
  const prior = byId.get("prior");
  const data = byId.get("data");
  const cross = byId.get("cross");
  if (prior === null || prior === undefined || data === null || data === undefined || cross === null || cross === undefined) return null;
  return robustnessWeights.prior * prior + robustnessWeights.data * data + robustnessWeights.cross * cross;
}

function robustnessBandValue(robustness?: TargetRobustness): string {
  return String(robustness?.absolute_band || robustness?.robustness_band || robustness?.band || getField(robustness?.source_row, ["absolute_band", "robustness_band"]) || "");
}

function robustnessBandMethod(robustness?: TargetRobustness): string {
  const method = String(robustness?.band_method || getField(robustness?.source_row, ["band_method"]) || "").replaceAll("_", " ");
  if (method.toLowerCase().includes("provisional fixed")) return "provisional fixed thresholds";
  return method || "provisional fixed thresholds";
}

function relativeRankLabel(robustness?: TargetRobustness): string {
  const label = String(robustness?.relative_rank_label || getField(robustness?.source_row, ["relative_rank_label"]) || "").trim();
  if (label) return label;
  const rank = asNumber(robustness?.relative_rank ?? getField(robustness?.source_row, ["relative_rank"]));
  const total = asNumber(robustness?.relative_rank_total ?? getField(robustness?.source_row, ["relative_rank_total"]));
  if (rank !== null && total !== null) return `${formatNumber(rank, 0)} / ${formatNumber(total, 0)} tested channels`;
  return "Unavailable";
}

function normalizedRobustnessSubscores(robustness?: TargetRobustness): Array<{ id: string; label: string; value: number | null }> {
  const source = robustness?.source_row;
  const fromSource = [
    {
      id: "prior",
      label: "Sensitivity Elasticity",
      value: scoreField(source, ["sensitivity_elasticity_score", "prior_sensitivity_subscore"]),
    },
    {
      id: "data",
      label: "Data Influence",
      value: scoreField(source, ["data_influence_score", "data_influence_subscore"]),
    },
    {
      id: "cross",
      label: "Cross-Channel",
      value: scoreField(source, ["cross_channel_score", "cross_channel_subscore"]),
    },
  ];
  if (fromSource.some((item) => item.value !== null)) return fromSource;

  return (robustness?.subscores || [])
    .filter((item) => !String(item.id || item.label || "").toLowerCase().includes("adstock"))
    .map((item) => {
      const raw = String(item.id || item.label || "").toLowerCase();
      const isPrior = raw.includes("prior") || raw.includes("sensitivity");
      return {
        id: item.id || (isPrior ? "prior" : item.label || "subscore"),
        label: isPrior ? "Sensitivity Elasticity" : item.label || item.id || "Subscore",
        value: asNumber(item.value),
      };
    });
}

function getField(row: Record<string, unknown> | undefined, keys: string[]): unknown {
  if (!row) return undefined;
  const key = keys.find((candidate) => row[candidate] !== undefined && row[candidate] !== null && row[candidate] !== "");
  return key ? row[key] : undefined;
}

function stabilityLabel(row: MovementRow): "Stable" | "Unstable" | "Review" {
  if (row.stablePct) return "Stable";
  if (row.baselineRoi === null) return "Review";
  return "Unstable";
}

function directionLabel(value: number | null): "increase" | "decrease" | "flat" {
  if (value === null || !Number.isFinite(value) || value === 0) return "flat";
  return value > 0 ? "increase" : "decrease";
}

function getSetting(settings: Array<{ label?: string; value?: string }> | undefined, label: string): string {
  return settings?.find((item) => item.label?.toLowerCase() === label.toLowerCase())?.value || "";
}

function normalizeSummary(summary: TargetChannelSummary | undefined): TargetChannelSummary {
  return summary || {};
}

function buildRows(summary: TargetChannelSummary, target: string, minReliableBaseline: number): MovementRow[] {
  const responseRows = summary.system_response_rows || [];
  const impactRows = new Map<string, SystemImpactRow>();
  (summary.system_impact_rows || []).forEach((row) => {
    const channel = String(row.channel || "").toLowerCase();
    if (channel) impactRows.set(channel, row);
  });

  const byChannel = new Map<string, Array<Record<string, unknown>>>();
  responseRows.forEach((row) => {
    const channel = String(row.channel || "").toLowerCase();
    if (!channel) return;
    byChannel.set(channel, [...(byChannel.get(channel) || []), row]);
  });
  impactRows.forEach((_, channel) => {
    if (!byChannel.has(channel)) byChannel.set(channel, []);
  });

  return [...byChannel.entries()]
    .map(([channel, rows]) => {
      const impact = impactRows.get(channel);
      const movementRows = rows.filter((row) => String(row.is_baseline || "").toLowerCase() !== "true");
      const pctValues = movementRows.map((row) => asNumber(row.signed_delta_pct));
      const deltaValues = movementRows.map((row) => asNumber(row.delta_abs));
      const baselineRoi = median(rows.map((row) => asNumber(row.roi_baseline)));
      const isSelf = Boolean(impact?.is_self_response) || channel === target.toLowerCase();
      const stablePct = baselineRoi !== null && Math.abs(baselineRoi) >= minReliableBaseline;
      return {
        channel,
        isSelf,
        baselineRoi,
        medianPct: median(pctValues),
        maxAbsPct: asNumber(impact?.max_abs_delta_pct) ?? absMax(pctValues),
        medianDeltaRoi: median(deltaValues),
        maxAbsDeltaRoi: asNumber(impact?.max_abs_delta_roi) ?? absMax(deltaValues),
        leftPct: asNumber(impact?.left_pct) ?? (pctValues.filter((v): v is number => Number.isFinite(v)).length ? Math.min(...pctValues.filter((v): v is number => Number.isFinite(v))) : null),
        rightPct: asNumber(impact?.right_pct) ?? (pctValues.filter((v): v is number => Number.isFinite(v)).length ? Math.max(...pctValues.filter((v): v is number => Number.isFinite(v))) : null),
        leftDeltaRoi: asNumber(impact?.left_delta_roi) ?? (deltaValues.filter((v): v is number => Number.isFinite(v)).length ? Math.min(...deltaValues.filter((v): v is number => Number.isFinite(v))) : null),
        rightDeltaRoi: asNumber(impact?.right_delta_roi) ?? (deltaValues.filter((v): v is number => Number.isFinite(v)).length ? Math.max(...deltaValues.filter((v): v is number => Number.isFinite(v))) : null),
        n: Number(impact?.n_rows ?? movementRows.length) || 0,
        stablePct,
      };
    })
    .sort((a, b) => (b.maxAbsPct ?? b.maxAbsDeltaRoi ?? -1) - (a.maxAbsPct ?? a.maxAbsDeltaRoi ?? -1));
}

function RobustnessCard({ robustness }: { robustness?: TargetRobustness }) {
  const [explainerOpen, setExplainerOpen] = useState(false);
  const subscores = normalizedRobustnessSubscores(robustness);
  const payloadScore = rawPayloadRobustnessScore(robustness);
  const calculatedScore = computedRobustnessScore(subscores);
  const scoreMismatch =
    payloadScore !== null &&
    calculatedScore !== null &&
    Math.abs(payloadScore - calculatedScore) > 0.5;
  const robustnessScore = calculatedScore ?? payloadScore;
  const robustnessBand = absoluteBandForScore(robustnessScore) || robustnessBandValue(robustness);
  const bandMethod = robustnessBandMethod(robustness);
  const rankLabel = relativeRankLabel(robustness);
  useEffect(() => {
    if (!scoreMismatch) return;
    console.warn("Prior Sensitivity robustness payload mismatch; using computed 3-component score.", {
      payloadScore,
      calculatedScore,
      subscores,
      sourceRow: robustness?.source_row,
    });
  }, [calculatedScore, payloadScore, robustness?.source_row, scoreMismatch, subscores]);

  useEffect(() => {
    if (!explainerOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setExplainerOpen(false);
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [explainerOpen]);

  return (
    <article className="content-panel ps-context-card ps-robust-card">
      <div className="ps-card-heading">
        <h3>Target-Level Robustness Framework</h3>
      </div>
      {robustness?.available ? (
        <>
          <div className="ps-robust-score">
            <span>Overall Robustness Score</span>
            <strong>{scoreText(robustnessScore)}</strong>
            <em className={`ps-band ${bandClass(robustnessBand)}`}>{robustnessBand || "Unavailable"}</em>
          </div>
          <p className="ps-band-method">{bandMethod}</p>
          <div className="ps-relative-rank">
            <span>Relative Rank</span>
            <strong>{rankLabel}</strong>
            <p>1 / N = most robust among tested channels. N / N = least robust in this run.</p>
          </div>
          {scoreMismatch ? (
            <p className="ps-payload-warning">
              Payload score did not match the current 60/25/15 formula, so this card is using the computed three-component score.
            </p>
          ) : null}
          <div className="ps-subscore-list">
            {subscores.map((item) => {
              const value = asNumber(item.value);
              return (
                <div className="ps-subscore" key={item.id || item.label}>
                  <div>
                    <span>{item.label || item.id || "Subscore"}</span>
                    <strong>{scoreText(value)}</strong>
                  </div>
                  <i style={{ width: `${Math.max(0, Math.min(100, value ?? 0))}%` }} />
                </div>
              );
            })}
          </div>
          <div className="ps-band-interpretation">
            <h4>Band Interpretation</h4>
            <p>{bandInterpretation(robustnessBand)}</p>
          </div>
          <button className="ps-robustness-explainer-trigger" type="button" onClick={() => setExplainerOpen(true)}>
            How robustness score is calculated
          </button>
          {explainerOpen ? (
            <div className="ps-modal-backdrop" role="presentation" onMouseDown={() => setExplainerOpen(false)}>
              <section
                className="ps-robustness-modal"
                role="dialog"
                aria-modal="true"
                aria-labelledby="ps-robustness-modal-title"
                onMouseDown={(event) => event.stopPropagation()}
              >
                <header>
                  <h3 id="ps-robustness-modal-title">How robustness score is calculated</h3>
                  <button type="button" aria-label="Close robustness score explanation" onClick={() => setExplainerOpen(false)}>
                    <span aria-hidden="true">×</span>
                  </button>
                </header>
                <div className="ps-robustness-modal-body">
                  <section>
                    <h4>Overall robustness score</h4>
                    <p>This is a project-defined prior sensitivity score, not an official Meridian metric. It summarizes how stable a channel's posterior ROI/contribution estimates remain when prior assumptions are perturbed under the selected structural profile.</p>
                  </section>
                  <section>
                    <h4>Score composition</h4>
                    <ul>
                      <li><strong>Sensitivity Elasticity (60%)</strong> — how much outputs move relative to the prior perturbation.</li>
                      <li><strong>Data Influence (25%)</strong> — how strongly the observed data stabilizes the result.</li>
                      <li><strong>Cross-Channel (15%)</strong> — how much other channels move when the selected target channel's prior changes.</li>
                    </ul>
                    <p>Higher scores mean less observed fragility under the tested prior grid.</p>
                  </section>
                  <section>
                    <h4>Notes</h4>
                    <ul>
                      <li><strong>Near-zero guard:</strong> when ROI percent movement is unstable, use contribution movement when available; otherwise use a log-scaled absolute ROI change.</li>
                      <li><strong>Robustness band:</strong> Low &lt; 50, Medium 50-74, High &gt;= 75. These project-defined thresholds can be recalibrated later.</li>
                      <li><strong>Relative Rank:</strong> shows where the current channel ranks among tested channels in this run. Rank 1 = most robust in this run.</li>
                    </ul>
                  </section>
                </div>
              </section>
            </div>
          ) : null}
        </>
      ) : (
        <div className="ps-empty-state">Target-level robustness is unavailable for this run.</div>
      )}
    </article>
  );
}

function ResponseChart({ rows, target, mode }: { rows: MovementRow[]; target: string; mode: MetricMode }) {
  const getLeft = (row: MovementRow) => (mode === "pct" ? row.leftPct : row.leftDeltaRoi);
  const getRight = (row: MovementRow) => (mode === "pct" ? row.rightPct : row.rightDeltaRoi);
  const getValue = (row: MovementRow) => (mode === "pct" ? row.medianPct : row.medianDeltaRoi);
  const maxExtent = Math.max(...rows.flatMap((row) => [Math.abs(getLeft(row) ?? 0), Math.abs(getRight(row) ?? 0), Math.abs(getValue(row) ?? 0)]), 1);

  if (!rows.length) {
    return <div className="ps-empty-state">Full-system response rows are unavailable for this target channel.</div>;
  }

  return (
    <div className="ps-response-chart" role="img" aria-label={`Full-system response to ${channelLabel(target)} prior changes`}>
      {rows.map((row) => {
        const left = getLeft(row) ?? 0;
        const right = getRight(row) ?? 0;
        const value = getValue(row);
        const leftWidth = Math.min(50, (Math.abs(Math.min(left, 0)) / maxExtent) * 50);
        const rightWidth = Math.min(50, (Math.abs(Math.max(right, 0)) / maxExtent) * 50);
        return (
          <div className={row.isSelf ? "ps-response-row ps-response-row--self" : "ps-response-row"} key={row.channel}>
            <div className="ps-response-channel">
              {row.isSelf ? <span aria-hidden="true">★</span> : null}
              {channelLabel(row.channel)}{row.isSelf ? " (self)" : ""}
            </div>
            <div className="ps-response-track">
              <span className="ps-response-axis" aria-hidden="true" />
              <span className="ps-response-bar ps-response-bar--negative" style={{ width: `${leftWidth}%` }} />
              <span className="ps-response-bar ps-response-bar--positive" style={{ width: `${rightWidth}%` }} />
            </div>
            <div className={`ps-response-value ${signedClass(value)}`}>
              {mode === "pct" ? signedPercent(value) : signedNumber(value)}
              {!row.stablePct && mode === "pct" ? <span title="Unstable percentage due to weak baseline">⚠</span> : null}
            </div>
          </div>
        );
      })}
      <div className="ps-response-axis-label">{mode === "pct" ? "% Change vs Baseline ROI" : "Delta ROI vs Baseline"}</div>
    </div>
  );
}

export function PriorSensitivityPage() {
  const result = useCurrentResult();
  const { payload } = result;
  const options = payload.target_channel_detail?.options || [];
  const summaries = payload.target_channel_detail?.summaries || {};
  const initialTarget = payload.target_channel_detail?.default_channel || options[0]?.value || Object.keys(summaries)[0] || "";
  const [selectedTarget, setSelectedTarget] = useState(initialTarget);
  const [metricMode, setMetricMode] = useState<MetricMode>("pct");
  const [selectorOpen, setSelectorOpen] = useState(false);
  const selectorRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!selectedTarget && initialTarget) setSelectedTarget(initialTarget);
  }, [initialTarget, selectedTarget]);

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

  const selectorOptions = options.length
    ? options.flatMap((option) => option.value ? [{ value: option.value, label: option.label }] : [])
    : selectedTarget
      ? [{ value: selectedTarget, label: channelLabel(selectedTarget) }]
      : [];
  const selectedOptionLabel = selectorOptions.find((option) => option.value === selectedTarget)?.label || channelLabel(selectedTarget);

  const summary = normalizeSummary(summaries[selectedTarget]);
  const minReliableBaseline = asNumber((payload.overview as Record<string, unknown> | undefined)?.pct_guardrail_min_abs_baseline_roi) ?? 0.05;
  const rows = useMemo(() => buildRows(summary, selectedTarget, minReliableBaseline), [summary, selectedTarget, minReliableBaseline]);
  const hasUnstablePct = rows.some((row) => !row.stablePct);
  const percentAvailable = rows.some((row) => row.medianPct !== null || row.maxAbsPct !== null);
  const deltaAvailable = rows.some((row) => row.medianDeltaRoi !== null || row.maxAbsDeltaRoi !== null);

  useEffect(() => {
    if (hasUnstablePct && deltaAvailable) setMetricMode("delta");
    else if (percentAvailable) setMetricMode("pct");
  }, [selectedTarget, hasUnstablePct, deltaAvailable, percentAvailable]);

  const selectedRows = rows;
  const rankingRows = [...selectedRows].sort((a, b) => Math.abs(b.medianPct ?? b.maxAbsPct ?? 0) - Math.abs(a.medianPct ?? a.maxAbsPct ?? 0));
  const selfRow = selectedRows.find((row) => row.isSelf);
  const robustness = summary.robustness;
  const settings = payload.how_this_was_run?.settings || [];
  const priorDist = selfRow ? "ROI" : getSetting(settings, "Prior mode") || missing;
  const gridType = getSetting(settings, "Run mode") || getSetting(settings, "Prior grid scope") || summary.system_source || missing;
  const gridSize = summary.prior_settings_tested ?? selfRow?.n ?? selectedRows.reduce((sum, row) => Math.max(sum, row.n), 0);
  const topIncrease = selectedRows.filter((row) => (metricMode === "pct" ? row.medianPct : row.medianDeltaRoi) !== null && ((metricMode === "pct" ? row.medianPct : row.medianDeltaRoi) as number) > 0).slice(0, 3);
  const topDecrease = selectedRows.filter((row) => (metricMode === "pct" ? row.medianPct : row.medianDeltaRoi) !== null && ((metricMode === "pct" ? row.medianPct : row.medianDeltaRoi) as number) < 0).slice(0, 3);
  const unstableRows = selectedRows.filter((row) => !row.stablePct);

  return (
    <SectionScaffold
      title="Prior Sensitivity"
      summary="Explore how the system responds when a target channel's prior assumptions are changed."
      sourceKind={result.sourceKind}
      runSummary={result.runSummary}
      buildResultsPath={result.buildResultsPath}
    >
      <div className="prior-sensitivity-page prior-sensitivity-page--drilldown">
        <section className="content-panel ps-target-selector-card">
          <div className="ps-target-selector-field" ref={selectorRef}>
            <span>Select Target Channel</span>
            <button
              className="ps-target-select-button"
              type="button"
              aria-haspopup="listbox"
              aria-expanded={selectorOpen}
              onClick={() => setSelectorOpen((open) => !open)}
            >
              {selectedTarget ? <ChannelLogo channel={selectedTarget} /> : null}
              <strong>{selectedOptionLabel}</strong>
              <span className="ps-target-select-chevron" aria-hidden="true" />
            </button>
            {selectorOpen ? (
              <div className="ps-target-select-menu" role="listbox" aria-label="Select target channel">
                {selectorOptions.map((option) => (
                  <button
                    className={option.value === selectedTarget ? "ps-target-select-option active" : "ps-target-select-option"}
                    type="button"
                    role="option"
                    aria-selected={option.value === selectedTarget}
                    value={option.value}
                    key={option.value}
                    onClick={() => {
                      setSelectedTarget(option.value);
                      setSelectorOpen(false);
                    }}
                  >
                    <ChannelLogo channel={option.value} />
                    <span>{option.label || channelLabel(option.value)}</span>
                  </button>
                ))}
              </div>
            ) : null}
          </div>
          <div className="ps-selector-callout">
            <span aria-hidden="true">i</span>
            <p>This view shows full-system response to the selected target channel's prior changes. Overview page summarizes only each channel's self-response.</p>
          </div>
        </section>

        <section className="ps-drilldown-layout">
          <aside className="ps-left-rail">
            <article className="content-panel ps-context-card">
              <h3>Target Channel Context</h3>
              <dl className="ps-context-list">
                <div><dt>Target channel</dt><dd>{selectedTarget ? channelLabel(selectedTarget) : missing}</dd></div>
                <div><dt>Prior grid</dt><dd>{gridType}{priorDist !== missing ? ` (${priorDist})` : ""}</dd></div>
                <div><dt>Grid size</dt><dd>{gridSize ? `${formatNumber(gridSize)} prior settings` : missing}</dd></div>
                <div><dt>Baseline ROI</dt><dd>{selfRow?.baselineRoi !== null && selfRow ? formatNumber(selfRow.baselineRoi, 3) : missing}</dd></div>
                <div><dt>Baseline period</dt><dd>{getSetting(settings, "Date range") || missing}</dd></div>
              </dl>
            </article>
            <RobustnessCard robustness={robustness} />
          </aside>

          <main className="ps-main-column">
            <article className="content-panel ps-full-system-card">
              <div className="ps-card-toolbar">
                <div>
                  <h3>Full-System Response to {channelLabel(selectedTarget)} Prior Changes</h3>
                  {hasUnstablePct ? <p>Some percentage changes are marked unstable because baseline ROI is weak; Delta ROI is available as fallback.</p> : null}
                </div>
                <div className="ps-metric-toggle" aria-label="Chart metric">
                  <span>View as</span>
                  <button className={metricMode === "pct" ? "active" : ""} type="button" disabled={!percentAvailable} onClick={() => setMetricMode("pct")}>% Change</button>
                  <button className={metricMode === "delta" ? "active" : ""} type="button" disabled={!deltaAvailable} onClick={() => setMetricMode("delta")}>Delta ROI</button>
                </div>
              </div>
              <ResponseChart rows={selectedRows} target={selectedTarget} mode={metricMode} />
              <div className="ps-chart-legend">
                <span><b>★</b> Target channel (self)</span>
                <span><i className="ps-legend-up" /> Increase vs baseline</span>
                <span><i className="ps-legend-down" /> Decrease vs baseline</span>
                <span><i className="ps-legend-warning" /> Unstable %</span>
              </div>
            </article>

            <section className="ps-detail-grid">
              <article className="content-panel ps-table-card">
                <h3>Movement Summary</h3>
                <div className="table-shell ps-table-shell">
                  <table className="ps-movement-table">
                    <thead>
                      <tr><th>Channel</th><th>Baseline ROI</th><th>Median %</th><th>Max Abs %</th><th>N</th></tr>
                    </thead>
                    <tbody>
                      {selectedRows.map((row) => (
                        <tr className={row.isSelf ? "ps-self-table-row" : ""} key={row.channel}>
                          <td>{channelLabel(row.channel)}{row.isSelf ? " (self)" : ""}</td>
                          <td>{row.baselineRoi !== null ? formatNumber(row.baselineRoi, 3) : "NA"}</td>
                          <td className={signedClass(row.medianPct)}>{signedPercent(row.medianPct)} {!row.stablePct ? <span className="ps-warning-pill">unstable</span> : null}</td>
                          <td>{row.maxAbsPct !== null ? formatPercent(row.maxAbsPct, 1) : "NA"}</td>
                          <td>{formatNumber(row.n)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </article>

              <article className="content-panel ps-table-card">
                <h3>Ranking by Absolute % Movement</h3>
                <div className="table-shell ps-table-shell">
                  <table className="ps-ranking-table">
                    <thead>
                      <tr><th>Rank</th><th>Channel</th><th>Abs %</th><th>Dir.</th><th>Stability</th></tr>
                    </thead>
                    <tbody>
                      {rankingRows.map((row, index) => {
                        const direction = directionLabel(row.medianPct);
                        return (
                          <tr className={row.isSelf ? "ps-self-table-row" : ""} key={row.channel}>
                            <td>{index + 1}</td>
                            <td>{channelLabel(row.channel)}{row.isSelf ? " (self)" : ""}</td>
                            <td>{row.medianPct !== null ? formatPercent(Math.abs(row.medianPct), 1) : "NA"}</td>
                            <td><span className={`ps-direction ps-direction--${direction}`} title={direction}>{direction === "increase" ? "↑" : direction === "decrease" ? "↓" : "→"}</span></td>
                            <td><span className={`ps-stability ps-stability--${stabilityLabel(row).toLowerCase()}`}>{stabilityLabel(row)}</span></td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </article>

              <aside className="content-panel ps-interpretation-card ps-drilldown-interpretation">
                <div className="ps-interpretation-title">
                  <span aria-hidden="true">i</span>
                  <h3>Interpretation</h3>
                </div>
                <div className="ps-interpretation-group ps-interpretation-group--first">
                  <h4>What this shows</h4>
                  <p>Shows how all channels respond when {channelLabel(selectedTarget)}'s prior assumptions change. Overview only summarizes each channel's self-response.</p>
                </div>
                <div className="ps-interpretation-group">
                  <h4>Top movers</h4>
                  <p>{topIncrease.length ? topIncrease.map((row) => channelLabel(row.channel)).join(", ") : "No positive movers available."}</p>
                </div>
                <div className="ps-interpretation-group">
                  <h4>Negative movers</h4>
                  <p>{topDecrease.length ? topDecrease.map((row) => channelLabel(row.channel)).join(", ") : "No negative movers available."}</p>
                </div>
                <div className="ps-interpretation-group">
                  <h4>Unstable % changes</h4>
                  <p>{unstableRows.length ? `${unstableRows.length} channel(s) have weak baseline ROI. Use Delta ROI if needed.` : "No unstable percentage changes flagged."}</p>
                </div>
              </aside>
            </section>
          </main>
        </section>

        <section className="ps-note-card">
          <span aria-hidden="true">i</span>
          <p>Note: This analysis varies only {channelLabel(selectedTarget)}'s prior while keeping other priors at baseline. Results reflect model outputs and should be interpreted within model assumptions.</p>
        </section>
      </div>
    </SectionScaffold>
  );
}
