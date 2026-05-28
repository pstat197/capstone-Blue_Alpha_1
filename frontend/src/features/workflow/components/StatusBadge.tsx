type StatusBadgeProps = {
  status: "valid" | "warning" | "missing" | "locked" | "mock" | "api";
  label?: string;
};

const labelByStatus: Record<StatusBadgeProps["status"], string> = {
  valid: "Valid",
  warning: "Warning",
  missing: "Missing",
  locked: "Locked",
  mock: "Available",
  api: "Valid",
};

function StatusIcon({ status }: { status: StatusBadgeProps["status"] }) {
  if (status === "warning") {
    return (
      <svg className="status-badge-svg" viewBox="0 0 20 20" aria-hidden="true">
        <path d="M10 3.2v8.2" />
        <path d="M10 15.8h.01" />
      </svg>
    );
  }

  if (status === "missing") {
    return (
      <svg className="status-badge-svg" viewBox="0 0 20 20" aria-hidden="true">
        <path d="M5.2 5.2l9.6 9.6" />
        <path d="M14.8 5.2l-9.6 9.6" />
      </svg>
    );
  }

  if (status === "locked") {
    return (
      <svg className="status-badge-svg" viewBox="0 0 20 20" aria-hidden="true">
        <path d="M5 10h10" />
      </svg>
    );
  }

  return (
    <svg className="status-badge-svg" viewBox="0 0 20 20" aria-hidden="true">
      <path d="M4.4 10.4l3.5 3.5 7.7-8" />
    </svg>
  );
}

export function StatusBadge({ status, label }: StatusBadgeProps) {
  if (label) {
    return <span className={`status-badge status-badge--${status}`}>{label}</span>;
  }

  return (
    <span className={`status-badge status-badge--${status} status-badge--icon`} aria-label={labelByStatus[status]}>
      <StatusIcon status={status} />
    </span>
  );
}
