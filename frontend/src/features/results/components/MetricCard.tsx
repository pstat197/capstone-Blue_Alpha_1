type MetricCardProps = {
  label: string;
  value: string;
  note?: string;
  icon?: "runs" | "channels" | "qc" | "kpi" | "scope";
  tone?: "blue" | "green" | "amber" | "violet";
};

export function MetricCard({ label, value, note, icon, tone = "blue" }: MetricCardProps) {
  return (
    <div className="metric-card">
      {icon ? <span className={`metric-icon metric-icon--${icon} metric-icon--${tone}`} aria-hidden="true" /> : null}
      <div className="metric-copy">
        <div className="metric-label">{label}</div>
        <div className="metric-value">{value}</div>
        {note ? <div className="metric-note">{note}</div> : null}
      </div>
    </div>
  );
}
