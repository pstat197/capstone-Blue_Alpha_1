import type { ReactNode } from "react";
import { useMemo } from "react";
import { SectionScaffold } from "../components/SectionScaffold";
import { ContextualHelpButton } from "../../../shared/ContextualHelp";
import { useCurrentResult } from "../data/resultLoader";
import type { DashboardPayload } from "../data/resultTypes";

type StructuralParam = {
  channel: string;
  alpha: number | null;
  ec: number | null;
  slope: number | null;
  maxLag: number | null;
};

type Point = {
  x: number;
  y: number;
};

type CurveSeries = {
  channel: string;
  color: string;
  points: Point[];
};

const chartColors = ["#1f6fff", "#22a06b", "#f59f00", "#7c4dff", "#d9486e", "#0f9fb3", "#a16207", "#536dfe"];

function toNumber(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string") {
    const cleaned = value.trim().replace(/,/g, "").replace("%", "");
    if (!cleaned || cleaned.toLowerCase() === "na" || cleaned.toLowerCase() === "unavailable") return null;
    const parsed = Number(cleaned);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function median(values: Array<number | null | undefined>): number | null {
  const numeric = values.filter((value): value is number => Number.isFinite(value));
  if (!numeric.length) return null;
  const sorted = [...numeric].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function formatValue(value: number | null, digits = 2): string {
  if (!Number.isFinite(value)) return "NA";
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(value as number);
}

function formatLag(value: number | null): string {
  if (!Number.isFinite(value)) return "NA";
  return Number.isInteger(value) ? String(value) : formatValue(value, 2);
}

function formatShare(value: number | null): string {
  if (!Number.isFinite(value)) return "Unavailable";
  return `${formatValue(value, 1)}%`;
}

function channelLabel(channel: string): string {
  return channel ? channel.toUpperCase() : "UNAVAILABLE";
}

function getField(row: Record<string, unknown>, keys: string[]): unknown {
  return keys.map((key) => row[key]).find((value) => value !== undefined && value !== null && value !== "");
}

function parseChannelsFromRunId(runId?: string | null): string[] {
  const parts = String(runId || "").split("|");
  if (parts[0] !== "multi" || !parts[1]) return [];
  return parts[1]
    .split(",")
    .map((channel) => channel.trim())
    .filter(Boolean);
}

function selectPayloadChannels(payload: DashboardPayload): string[] {
  const fromRunId = parseChannelsFromRunId(payload.structural?.selected_run_id);
  if (fromRunId.length) return fromRunId;
  const fromTargetOptions = payload.target_channel_detail?.options?.map((option) => String(option.value || "").trim()).filter(Boolean) || [];
  return [...new Set(fromTargetOptions)];
}

function structuralKey(param: StructuralParam): string {
  return [param.alpha, param.ec, param.slope, param.maxLag].map((value) => (value === null ? "NA" : String(value))).join("|");
}

function buildStructuralParams(payload: DashboardPayload): StructuralParam[] {
  const structural = payload.structural;
  const selectedRunId = structural?.selected_run_id;
  const selectedChannels = new Set(selectPayloadChannels(payload).map((channel) => channel.toLowerCase()));
  const responseRows = structural?.response_rows || [];
  const filteredResponseRows =
    selectedRunId && responseRows.some((row) => String(row.run_id || "") === selectedRunId)
      ? responseRows.filter((row) => String(row.run_id || "") === selectedRunId)
      : responseRows;

  const sourceRows = filteredResponseRows.length ? filteredResponseRows : payload.workbench?.run_rows || [];
  const byChannel = new Map<string, StructuralParam>();

  sourceRows.forEach((row) => {
    const channel = String(getField(row, ["channel", "target_channel"]) || "").trim();
    if (!channel) return;
    const existing = byChannel.get(channel) || {
      channel,
      alpha: null,
      ec: null,
      slope: null,
      maxLag: null,
    };
    const alpha = toNumber(getField(row, ["adstock_alpha_m", "alpha", "adstock_alpha"]));
    const ec = toNumber(getField(row, ["saturation_ec_m", "ec", "ec_m"]));
    const slope = toNumber(getField(row, ["saturation_slope_m", "slope", "hill_slope"]));
    const maxLag = toNumber(getField(row, ["max_lag", "lag"]));
    byChannel.set(channel, {
      channel,
      alpha: existing.alpha ?? alpha,
      ec: existing.ec ?? ec,
      slope: existing.slope ?? slope,
      maxLag: existing.maxLag ?? maxLag,
    });
  });

  if (byChannel.size) {
    const rows = [...byChannel.values()];
    const scopedRows = selectedChannels.size ? rows.filter((row) => selectedChannels.has(row.channel.toLowerCase())) : rows;
    return scopedRows.sort((a, b) => a.channel.localeCompare(b.channel));
  }

  const profile = structural?.profile_rows?.[0];
  if (!profile) return [];
  return [
    {
      channel: "Aggregate",
      alpha: toNumber(getField(profile, ["adstock_alpha_m", "alpha", "adstock_alpha"])),
      ec: toNumber(getField(profile, ["saturation_ec_m", "ec", "ec_m"])),
      slope: toNumber(getField(profile, ["saturation_slope_m", "slope", "hill_slope"])),
      maxLag: toNumber(getField(profile, ["max_lag", "lag"])),
    },
  ];
}

function geometricHalfLife(alpha: number | null): number | null {
  if (!Number.isFinite(alpha) || alpha === null || alpha <= 0 || alpha >= 1) return null;
  return Math.log(0.5) / Math.log(alpha);
}

function adstockPoints(alpha: number | null, maxLag: number | null): Point[] {
  if (!Number.isFinite(alpha) || alpha === null || alpha < 0 || alpha >= 1) return [];
  const lagLimit = Math.max(1, Math.round(maxLag ?? 8));
  return Array.from({ length: lagLimit + 1 }, (_, lag) => ({ x: lag, y: Math.pow(alpha, lag) }));
}

function lagResponsePoints(payload: DashboardPayload, alpha: number | null, maxLag: number | null): Point[] {
  const structural = payload.structural;
  const selectedRunId = structural?.selected_run_id;
  const selectedProfileId = structural?.selected_profile_id;
  const sourceRows = [...(structural?.carryover_rows || []), ...(structural?.adstock_curve_rows || [])];
  const filteredRows = sourceRows.filter((row) => {
    const runMatches = !selectedRunId || !row.run_id || String(row.run_id) === selectedRunId;
    const profileMatches = !selectedProfileId || !row.struct_profile_id || String(row.struct_profile_id) === selectedProfileId;
    return runMatches && profileMatches;
  });
  const parsed = filteredRows
    .map((row) => {
      const x = toNumber(getField(row, ["lag", "lag_period", "period", "x"]));
      const y = toNumber(getField(row, ["relative_response", "response", "weight", "adstock_weight", "y"]));
      return x === null || y === null ? null : { x, y };
    })
    .filter((point): point is Point => point !== null)
    .sort((a, b) => a.x - b.x);

  if (!parsed.length) return adstockPoints(alpha, maxLag);
  const base = parsed.find((point) => point.x === 0)?.y || Math.max(...parsed.map((point) => point.y));
  return base > 0 ? parsed.map((point) => ({ x: point.x, y: point.y / base })) : parsed;
}

function avgLagFromPoints(points: Point[]): number | null {
  const total = points.reduce((sum, point) => sum + point.y, 0);
  if (!total) return null;
  return points.reduce((sum, point) => sum + point.x * point.y, 0) / total;
}

function immediateShareFromPoints(points: Point[]): number | null {
  const total = points.reduce((sum, point) => sum + point.y, 0);
  if (!total) return null;
  const immediatePoint = points.find((point) => point.x === 0) || points[0];
  return (immediatePoint.y / total) * 100;
}

function hillResponse(x: number, ec: number, slope: number): number {
  const xp = Math.pow(x, slope);
  const ecp = Math.pow(ec, slope);
  const denominator = ecp + xp;
  return denominator ? xp / denominator : 0;
}

function saturationPoints(ec: number | null, slope: number | null): Point[] {
  if (!Number.isFinite(ec) || !Number.isFinite(slope) || ec === null || slope === null || ec <= 0 || slope <= 0) return [];
  return Array.from({ length: 80 }, (_, index) => {
    const t = index / 79;
    const x = Math.pow(10, -2 + t * 4);
    return { x, y: hillResponse(x, ec, slope) };
  });
}

function pathFromPoints(points: Point[], xScale: (x: number) => number, yScale: (y: number) => number): string {
  return points.map((point, index) => `${index === 0 ? "M" : "L"} ${xScale(point.x).toFixed(2)} ${yScale(point.y).toFixed(2)}`).join(" ");
}

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

function MissingState({ children }: { children: ReactNode }) {
  return <div className="model-structure-missing">{children}</div>;
}

function SummaryCard({
  title,
  value,
  subtitle,
}: {
  title: string;
  value: string;
  subtitle: string;
}) {
  return (
    <article className="ms-summary-card">
      <div>
        <span>{title}</span>
        <strong>{value}</strong>
        <p>{subtitle}</p>
      </div>
    </article>
  );
}

function Note({ children }: { children: ReactNode }) {
  return (
    <div className="ms-card-note">
      <span aria-hidden="true">i</span>
      <p>{children}</p>
    </div>
  );
}

function CarryoverChart({ alpha, maxLag, points }: { alpha: number | null; maxLag: number | null; points: Point[] }) {
  if (!points.length) return <MissingState>Carryover decay profile is unavailable because alpha is missing for this run.</MissingState>;

  const width = 640;
  const height = 230;
  const pad = { left: 58, right: 26, top: 24, bottom: 42 };
  const maxX = points[points.length - 1].x || 1;
  const xScale = (x: number) => pad.left + (x / maxX) * (width - pad.left - pad.right);
  const yScale = (y: number) => pad.top + (1 - y) * (height - pad.top - pad.bottom);
  const halfLife = geometricHalfLife(alpha);
  const halfX = halfLife !== null ? Math.min(maxX, Math.max(0, halfLife)) : null;

  return (
    <svg className="ms-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Carryover decay profile chart">
      <line className="ms-axis" x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} />
      <line className="ms-axis" x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} />
      {[0, 0.25, 0.5, 0.75, 1].map((tick) => (
        <g key={tick}>
          <line className={tick === 0.5 ? "ms-guide ms-guide--strong" : "ms-gridline"} x1={pad.left} x2={width - pad.right} y1={yScale(tick)} y2={yScale(tick)} />
          <text className="ms-tick" x={pad.left - 10} y={yScale(tick) + 4} textAnchor="end">{formatValue(tick, 2)}</text>
        </g>
      ))}
      {points.map((point) => (
        <g key={point.x}>
          <line className="ms-gridline ms-gridline--x" x1={xScale(point.x)} x2={xScale(point.x)} y1={height - pad.bottom} y2={height - pad.bottom + 5} />
          <text className="ms-tick" x={xScale(point.x)} y={height - 16} textAnchor="middle">{point.x}</text>
        </g>
      ))}
      {halfX !== null ? <line className="ms-guide" x1={xScale(halfX)} x2={xScale(halfX)} y1={pad.top} y2={height - pad.bottom} /> : null}
      <path className="ms-line ms-line--blue" d={pathFromPoints(points, xScale, yScale)} />
      {points.map((point) => (
        <circle className="ms-dot" key={`${point.x}-${point.y}`} cx={xScale(point.x)} cy={yScale(point.y)} r="4" />
      ))}
      {halfX !== null ? (
        <g className="ms-annotation">
          <rect x={xScale(halfX) + 16} y={yScale(0.5) - 30} width="116" height="48" rx="8" />
          <text x={xScale(halfX) + 30} y={yScale(0.5) - 12}>Half-Life</text>
          <text x={xScale(halfX) + 30} y={yScale(0.5) + 8}>{formatValue(halfLife, 3)} periods</text>
        </g>
      ) : null}
      <text className="ms-axis-label" x={width / 2} y={height - 2} textAnchor="middle">Lag (periods)</text>
      <text className="ms-axis-label" x={16} y={height / 2} textAnchor="middle" transform={`rotate(-90 16 ${height / 2})`}>Relative Response</text>
    </svg>
  );
}

function SaturationChart({ params, aggregateEc, aggregateSlope }: { params: StructuralParam[]; aggregateEc: number | null; aggregateSlope: number | null }) {
  const medianPoints = saturationPoints(aggregateEc, aggregateSlope);
  if (!medianPoints.length) return <MissingState>Saturation response curve is unavailable because EC or slope is missing for this run.</MissingState>;

  const width = 740;
  const height = 260;
  const pad = { left: 64, right: 28, top: 24, bottom: 46 };
  const xScale = (x: number) => pad.left + ((Math.log10(x) + 2) / 4) * (width - pad.left - pad.right);
  const yScale = (y: number) => pad.top + (1 - Math.min(1.25, Math.max(0, y)) / 1.25) * (height - pad.top - pad.bottom);
  const bandAvailable = params.filter((param) => param.ec !== null && param.slope !== null).length > 1;
  const bandTop = bandAvailable
    ? medianPoints.map((point) => {
        const values = params
          .filter((param) => param.ec !== null && param.slope !== null)
          .map((param) => hillResponse(point.x, param.ec as number, param.slope as number));
        return { x: point.x, y: Math.max(...values) };
      })
    : [];
  const bandBottom = bandAvailable
    ? medianPoints.map((point) => {
        const values = params
          .filter((param) => param.ec !== null && param.slope !== null)
          .map((param) => hillResponse(point.x, param.ec as number, param.slope as number));
        return { x: point.x, y: Math.min(...values) };
      })
    : [];
  const bandPath = bandAvailable
    ? `${pathFromPoints(bandTop, xScale, yScale)} ${[...bandBottom].reverse().map((point) => `L ${xScale(point.x).toFixed(2)} ${yScale(point.y).toFixed(2)}`).join(" ")} Z`
    : "";

  return (
    <svg className="ms-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Saturation response curve chart">
      <line className="ms-axis" x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} />
      <line className="ms-axis" x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} />
      {[0, 0.25, 0.5, 0.75, 1, 1.25].map((tick) => (
        <g key={tick}>
          <line className={tick === 0.5 ? "ms-guide ms-guide--strong" : "ms-gridline"} x1={pad.left} x2={width - pad.right} y1={yScale(tick)} y2={yScale(tick)} />
          <text className="ms-tick" x={pad.left - 10} y={yScale(tick) + 4} textAnchor="end">{formatValue(tick, 2)}</text>
        </g>
      ))}
      {[0.01, 0.1, 1, 10, 100].map((tick) => (
        <g key={tick}>
          <line className="ms-gridline ms-gridline--x" x1={xScale(tick)} x2={xScale(tick)} y1={height - pad.bottom} y2={height - pad.bottom + 5} />
          <text className="ms-tick" x={xScale(tick)} y={height - 17} textAnchor="middle">{tick}</text>
        </g>
      ))}
      {bandAvailable ? <path className="ms-band" d={bandPath} /> : null}
      <line className="ms-guide" x1={xScale(aggregateEc as number)} x2={xScale(aggregateEc as number)} y1={yScale(0.5)} y2={height - pad.bottom} />
      <path className="ms-line ms-line--blue" d={pathFromPoints(medianPoints, xScale, yScale)} />
      <circle className="ms-dot ms-dot--hollow" cx={xScale(aggregateEc as number)} cy={yScale(0.5)} r="4.5" />
      <g className="ms-annotation">
        <rect x={Math.max(pad.left + 10, xScale(aggregateEc as number) - 130)} y={yScale(0.5) - 58} width="108" height="50" rx="8" />
        <text x={Math.max(pad.left + 24, xScale(aggregateEc as number) - 116)} y={yScale(0.5) - 38}>EC Midpoint</text>
        <text x={Math.max(pad.left + 24, xScale(aggregateEc as number) - 116)} y={yScale(0.5) - 18}>{formatValue(aggregateEc, 2)}</text>
      </g>
      <g className="ms-annotation">
        <rect x={Math.min(width - 128, xScale(Math.max(aggregateEc as number, 1)) + 42)} y={yScale(0.5) - 34} width="86" height="52" rx="8" />
        <text x={Math.min(width - 114, xScale(Math.max(aggregateEc as number, 1)) + 56)} y={yScale(0.5) - 14}>Slope</text>
        <text x={Math.min(width - 114, xScale(Math.max(aggregateEc as number, 1)) + 56)} y={yScale(0.5) + 7}>{formatValue(aggregateSlope, 2)}</text>
      </g>
      <text className="ms-axis-label" x={width / 2} y={height - 2} textAnchor="middle">Spend Index</text>
      <text className="ms-axis-label" x={17} y={height / 2} textAnchor="middle" transform={`rotate(-90 17 ${height / 2})`}>Normalized Response</text>
    </svg>
  );
}

function ChannelCurvesChart({ series }: { series: CurveSeries[] }) {
  if (!series.length) return <MissingState>Channel-level response curves are unavailable for this run.</MissingState>;

  const width = 520;
  const height = 220;
  const pad = { left: 54, right: 22, top: 18, bottom: 42 };
  const xScale = (x: number) => pad.left + ((Math.log10(x) + 2) / 4) * (width - pad.left - pad.right);
  const yScale = (y: number) => pad.top + (1 - Math.min(1, Math.max(0, y))) * (height - pad.top - pad.bottom);

  return (
    <svg className="ms-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Channel response curves chart">
      <line className="ms-axis" x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} />
      <line className="ms-axis" x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} />
      {[0, 0.5, 1].map((tick) => (
        <g key={tick}>
          <line className="ms-gridline" x1={pad.left} x2={width - pad.right} y1={yScale(tick)} y2={yScale(tick)} />
          <text className="ms-tick" x={pad.left - 9} y={yScale(tick) + 4} textAnchor="end">{formatValue(tick, 2)}</text>
        </g>
      ))}
      {[0.01, 0.1, 1, 10, 100].map((tick) => (
        <text className="ms-tick" key={tick} x={xScale(tick)} y={height - 16} textAnchor="middle">{tick}</text>
      ))}
      {series.map((item) => (
        <path key={item.channel} d={pathFromPoints(item.points, xScale, yScale)} fill="none" stroke={item.color} strokeWidth="2.5" />
      ))}
      <text className="ms-axis-label" x={width / 2} y={height - 1} textAnchor="middle">Spend Index</text>
      <text className="ms-axis-label" x={16} y={height / 2} textAnchor="middle" transform={`rotate(-90 16 ${height / 2})`}>Norm. Response</text>
    </svg>
  );
}

export function ModelStructurePage() {
  const result = useCurrentResult();
  const { payload } = result;
  const params = useMemo(() => buildStructuralParams(payload), [payload]);
  const uniqueStructuralKeys = new Set(params.map(structuralKey));
  const usesSharedStructuralProfile = params.length > 1 && uniqueStructuralKeys.size === 1;
  const aggregateAlpha = median(params.map((param) => param.alpha));
  const aggregateEc = median(params.map((param) => param.ec));
  const aggregateSlope = median(params.map((param) => param.slope));
  const aggregateMaxLag = median(params.map((param) => param.maxLag));
  const halfLife = geometricHalfLife(aggregateAlpha);
  const carryoverPoints = lagResponsePoints(payload, aggregateAlpha, aggregateMaxLag);
  const avgLag = avgLagFromPoints(carryoverPoints);
  const immediate = immediateShareFromPoints(carryoverPoints);
  const carryover = immediate === null ? null : 100 - immediate;
  const isChannelAggregate = params.length > 1;
  const aggregateSubtitle = usesSharedStructuralProfile
    ? "shared across selected channels"
    : isChannelAggregate
      ? "median across channels"
      : "controls carryover decay";
  const uniqueParams = [...new Map(params.map((param) => [structuralKey(param), param])).values()];
  const chartParams = usesSharedStructuralProfile ? uniqueParams : params;
  const channelSeries = usesSharedStructuralProfile
    ? saturationPoints(aggregateEc, aggregateSlope).length
      ? [
          {
            channel: "Shared structural response curve",
            color: chartColors[0],
            points: saturationPoints(aggregateEc, aggregateSlope),
          },
        ]
      : []
    : params
        .filter((param) => param.channel !== "Aggregate" && param.ec !== null && param.slope !== null)
        .map((param, index) => ({
          channel: param.channel,
          color: chartColors[index % chartColors.length],
          points: saturationPoints(param.ec, param.slope),
        }))
        .filter((series) => series.points.length);
  const sharedProfileRows = [
    ["Alpha", formatValue(aggregateAlpha, 2)],
    ["EC Midpoint", formatValue(aggregateEc, 2)],
    ["Response Slope", formatValue(aggregateSlope, 2)],
    ["Max Lag", formatLag(aggregateMaxLag)],
    ["Half-Life", formatValue(halfLife, 2)],
  ];
  const tableRows = params.filter((param) => param.channel !== "Aggregate").length ? params.filter((param) => param.channel !== "Aggregate") : params;

  const handleCsv = () => {
    const rows = [
      ["Channel", "Alpha", "EC", "Slope", "Max Lag", "Half-Life"],
      ...tableRows.map((param) => [
        channelLabel(param.channel),
        param.alpha ?? "Unavailable",
        param.ec ?? "Unavailable",
        param.slope ?? "Unavailable",
        param.maxLag ?? "Unavailable",
        geometricHalfLife(param.alpha) ?? "Unavailable",
      ]),
    ];
    downloadText(
      `model-structure-table-${result.activeRunId || "run"}.csv`,
      rows.map((row) => row.map(csvEscape).join(",")).join("\n"),
      "text/csv"
    );
  };

  return (
    <SectionScaffold
      title="Model Structure"
      summary="Inspect the structural assumptions behind carryover, saturation, and response behavior."
      sourceLabel={result.sourceLabel}
      sourceDetail={result.sourceDetail}
      sourceKind={result.sourceKind}
      activeRunId={result.activeRunId}
      runSummary={result.runSummary}
      buildResultsPath={result.buildResultsPath}
      headerAside={null}
    >
      <div className="model-structure-page">
        <section className="ms-summary-grid" aria-label="Model structure summary">
          <SummaryCard title="Alpha / Adstock Memory" value={formatValue(aggregateAlpha, 2)} subtitle={aggregateSubtitle} />
          <SummaryCard title="EC Midpoint" value={formatValue(aggregateEc, 2)} subtitle={usesSharedStructuralProfile ? "shared across selected channels" : isChannelAggregate ? "median across channels" : "spend index at 50% response"} />
          <SummaryCard title="Response Slope" value={formatValue(aggregateSlope, 2)} subtitle={usesSharedStructuralProfile ? "shared across selected channels" : isChannelAggregate ? "median across channels" : "steepness of response curve"} />
          <SummaryCard title="Max Lag" value={formatLag(aggregateMaxLag)} subtitle={usesSharedStructuralProfile ? "shared across selected channels" : isChannelAggregate ? "median across channels" : "maximum lag periods included"} />
        </section>

        <section className="ms-top-grid">
          <article className="content-panel ms-chart-card">
            <div className="ms-card-header">
              <div>
                <h3>Carryover Decay Profile</h3>
                <p>Response contribution by lag period (geometric adstock).</p>
              </div>
              <div className="ms-stat-chips">
                <span><strong>{formatValue(halfLife, 3)}</strong>Half-Life</span>
                <span><strong>{formatValue(avgLag, 3)}</strong>Avg Lag</span>
              </div>
            </div>
            <CarryoverChart alpha={aggregateAlpha} maxLag={aggregateMaxLag} points={carryoverPoints} />
            <Note>
              {halfLife !== null && avgLag !== null
                ? `Response falls to 50% after ${formatValue(halfLife, 3)} periods. Average lag of impact is ${formatValue(avgLag, 3)} periods.`
                : "Carryover half-life and average lag are unavailable for this run."}
            </Note>
          </article>

          <article className="content-panel ms-chart-card">
            <div className="ms-card-header">
              <div>
                <h3>Saturation / Response Curve</h3>
                <p>Hill-type response function (spend index vs. normalized response).</p>
              </div>
              <div className="ms-chart-legend">
                <span><i />Median Response</span>
                <span><i />Reference Guides</span>
              </div>
            </div>
            <SaturationChart params={chartParams} aggregateEc={aggregateEc} aggregateSlope={aggregateSlope} />
            <Note>EC midpoint is the spend index at which response reaches 50% of its maximum.</Note>
          </article>
        </section>

        <section className="ms-bottom-grid">
          <article className="content-panel ms-chart-card">
            <div className="ms-card-header">
              <div>
                <h3>{usesSharedStructuralProfile ? "Shared Response Curve" : "Channel Response Curves"}</h3>
                <p>{usesSharedStructuralProfile ? "One global saturation curve used by all selected channels." : "Median saturation curves by channel (normalized)."}</p>
              </div>
            </div>
            {channelSeries.length ? (
              <div className="ms-compact-legend">
                {channelSeries.map((series) => (
                  <span key={series.channel}><i style={{ background: series.color }} />{usesSharedStructuralProfile ? series.channel : channelLabel(series.channel)}</span>
                ))}
              </div>
            ) : null}
            <ChannelCurvesChart series={channelSeries} />
            <Note>{usesSharedStructuralProfile ? "The repeated channel rows in the source payload share the same structural assumptions, so only one curve is shown." : "Curves show median structural shape by channel for comparison only."}</Note>
          </article>

          <article className="content-panel ms-readout-card">
            <div className="ms-card-header">
              <div>
                <h3>Structural Readout</h3>
                <p>{usesSharedStructuralProfile ? "Key metrics for the global structural profile." : "Key structural metrics aggregated across channels."}</p>
              </div>
            </div>
            <div className="ms-readout-grid">
              <div className="ms-readout-tile">
                <span>Immediate Share</span>
                <strong>{formatShare(immediate)}</strong>
                <p>impact in period 0</p>
              </div>
              <div className="ms-readout-tile">
                <span>Carryover Share</span>
                <strong>{formatShare(carryover)}</strong>
                <p>impact from lags 1+</p>
              </div>
              <div className="ms-readout-tile">
                <span>Current Alpha</span>
                <strong>{formatValue(aggregateAlpha, 2)}</strong>
                <p>{usesSharedStructuralProfile ? "shared adstock memory" : isChannelAggregate ? "median adstock memory" : "adstock memory"}</p>
              </div>
              <div className="ms-readout-tile">
                <span>Current EC / Slope</span>
                <strong>{aggregateEc !== null && aggregateSlope !== null ? `${formatValue(aggregateEc, 2)} / ${formatValue(aggregateSlope, 2)}` : "Unavailable"}</strong>
                <p>{usesSharedStructuralProfile ? "shared midpoint / steepness" : isChannelAggregate ? "median midpoint / steepness" : "midpoint / steepness"}</p>
              </div>
            </div>
            <Note>
              {aggregateMaxLag !== null
                ? `Shares calculated over lags 0-${formatLag(aggregateMaxLag)}. EC at 50% of max response.`
                : "Shares unavailable because max lag or alpha is missing."}
            </Note>
          </article>

          <article className="content-panel ms-table-card">
            <div className="ms-card-header ms-card-header--table">
              <div>
                <h3>{usesSharedStructuralProfile ? "Shared Structural Profile" : "Channel Structure Table"}</h3>
                <p>{usesSharedStructuralProfile ? "Global structural assumptions used for this run." : "Structural parameters by channel, median across runs."}</p>
              </div>
              {usesSharedStructuralProfile ? null : <button className="ms-secondary-button" type="button" onClick={handleCsv}>Download CSV</button>}
            </div>
            {usesSharedStructuralProfile ? (
              <div className="ms-shared-profile-grid">
                {sharedProfileRows.map(([label, value]) => (
                  <div key={label}>
                    <span>{label}</span>
                    <strong>{value}</strong>
                  </div>
                ))}
              </div>
            ) : tableRows.length ? (
              <div className="table-shell ms-table-shell">
                <table>
                  <thead>
                    <tr>
                      <th>Channel</th>
                      <th>Alpha <ContextualHelpButton sectionId="structural-alpha" label="Explain alpha" /></th>
                      <th>EC <ContextualHelpButton sectionId="structural-ec" label="Explain EC" /></th>
                      <th>Slope <ContextualHelpButton sectionId="structural-slope" label="Explain slope" /></th>
                      <th>Max Lag</th>
                      <th>Half-Life <ContextualHelpButton sectionId="structural-half-life" label="Explain half-life" /></th>
                    </tr>
                  </thead>
                  <tbody>
                    {tableRows.map((param) => (
                      <tr key={param.channel}>
                        <td><strong>{channelLabel(param.channel)}</strong></td>
                        <td>{formatValue(param.alpha, 2)}</td>
                        <td>{formatValue(param.ec, 2)}</td>
                        <td>{formatValue(param.slope, 2)}</td>
                        <td>{formatLag(param.maxLag)}</td>
                        <td>{formatValue(geometricHalfLife(param.alpha), 2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <MissingState>Channel-level structural parameters are unavailable for this run.</MissingState>
            )}
            <Note>{usesSharedStructuralProfile ? "This run does not define separate structural parameters per channel." : "Parameters reflect structural assumptions used in the final model."}</Note>
          </article>
        </section>

        <aside className="ms-warning-callout">
          <span aria-hidden="true">!</span>
          <p>These are structural profile diagnostics used to interpret how media impact accumulates and saturates over time and spend. <strong>They are not performance rankings or recommendations.</strong></p>
        </aside>
      </div>
    </SectionScaffold>
  );
}
