import { channelLabel, formatPercent } from "../data/resultSelectors";
import type { RoiTornadoRow } from "../data/resultTypes";

type TornadoChartProps = {
  rows: RoiTornadoRow[];
  compact?: boolean;
};

function formatSignedPercent(value: unknown, side: "negative" | "positive"): string {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "N/A";
  if (numeric === 0) return "0.0%";
  const magnitude = Math.abs(numeric);
  const sign = side === "negative" ? "-" : "+";
  return `${sign}${formatPercent(magnitude, 1)}`;
}

export function TornadoChart({ rows, compact = false }: TornadoChartProps) {
  const maxImpact = Math.max(
    ...rows.flatMap((row) => [row.left, row.right, row.impact].map((value) => Math.abs(Number(value))).filter(Number.isFinite)),
    1
  );
  const visibleRows = compact ? rows.slice(0, 8) : rows;

  if (!visibleRows.length) {
    return <div className="empty-state">Not available</div>;
  }

  return (
    <div className={compact ? "tornado-chart tornado-chart--compact" : "tornado-chart"} role="img" aria-label="Self-response tornado chart">
      {visibleRows.map((row) => {
        const left = Number(row.left ?? 0);
        const right = Number(row.right ?? 0);
        const leftWidth = Math.min(50, (Math.abs(left) / maxImpact) * 50);
        const rightWidth = Math.min(50, (Math.abs(right) / maxImpact) * 50);

        return (
          <div className="tornado-row" key={String(row.channel)}>
            <div className="tornado-channel">{channelLabel(row.channel)}</div>
            <div className="tornado-value tornado-value--negative">{formatSignedPercent(row.left, "negative")}</div>
            <div className="tornado-bars">
              <span className="tornado-axis" aria-hidden="true" />
              <span className="tornado-bar tornado-bar--left" style={{ width: `${leftWidth}%` }} />
              <span className="tornado-bar tornado-bar--right" style={{ width: `${rightWidth}%` }} />
            </div>
            <div className="tornado-value tornado-value--positive">{formatSignedPercent(row.right, "positive")}</div>
          </div>
        );
      })}
      {compact ? (
        <div className="tornado-scale" aria-hidden="true">
          <span />
          <span />
          <div className="tornado-scale-axis">
            <span>-{formatPercent(maxImpact, 0)}</span>
            <span>0%</span>
            <span>+{formatPercent(maxImpact, 0)}</span>
          </div>
          <span />
        </div>
      ) : null}
    </div>
  );
}
