import { channelLabel, formatPercent } from "../data/resultSelectors";
import type { RoiTornadoRow } from "../data/resultTypes";

type TornadoChartProps = {
  rows: RoiTornadoRow[];
  compact?: boolean;
};

export function TornadoChart({ rows, compact = false }: TornadoChartProps) {
  const maxImpact = Math.max(...rows.map((row) => Math.abs(Number(row.impact ?? 0))), 1);
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
            <div className="tornado-bars">
              <span className="tornado-axis" aria-hidden="true" />
              <span className="tornado-bar tornado-bar--left" style={{ width: `${leftWidth}%` }} />
              <span className="tornado-bar tornado-bar--right" style={{ width: `${rightWidth}%` }} />
            </div>
            <div className="tornado-value">{formatPercent(row.impact, 1)}</div>
          </div>
        );
      })}
      {compact ? (
        <div className="tornado-scale" aria-hidden="true">
          <span>-{formatPercent(maxImpact, 0)}</span>
          <span>0%</span>
          <span>+{formatPercent(maxImpact, 0)}</span>
        </div>
      ) : null}
    </div>
  );
}
