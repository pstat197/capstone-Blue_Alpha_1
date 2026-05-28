type MetricCardProps = {
  label: string;
  value: string;
  note?: string;
};

export function MetricCard({ label, value, note }: MetricCardProps) {
  return (
    <div className="metric-card">
      <div className="metric-copy">
        <div className="metric-label">{label}</div>
        <div className="metric-value">{value}</div>
        {note ? <div className="metric-note">{note}</div> : null}
      </div>
    </div>
  );
}
