import type { ChangeEvent } from "react";
import { useMemo, useState } from "react";
import { WorkflowScaffold } from "../components/WorkflowScaffold";
import { revenuePerKpiStorageKey } from "../data/mockWorkflow";
import {
  kpiColumnStorageKey,
  kpiTypeStorageKey,
  readActiveProfile,
  readKpiColumn,
  readKpiType,
  readRevenueColumn,
  readRevenuePerKpi,
  revenueColumnStorageKey,
} from "../data/workflowState";

type ProductIcon = "table" | "tag" | "dollar" | "target";

function IconBadge({ icon }: { icon: ProductIcon }) {
  return <span className={`product-icon product-icon--${icon}`} aria-hidden="true" />;
}

function KpiSummaryCard({
  icon,
  label,
  value,
  note,
}: {
  icon: ProductIcon;
  label: string;
  value: string;
  note: string;
}) {
  return (
    <article className="kpi-summary-card">
      <IconBadge icon={icon} />
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <p>{note}</p>
      </div>
    </article>
  );
}

export function KpiRevenuePage() {
  const profile = useMemo(() => readActiveProfile(), []);
  const [kpiColumn, setKpiColumn] = useState(() => readKpiColumn(profile));
  const [kpiType, setKpiType] = useState(() => readKpiType(profile));
  const [revenueColumn, setRevenueColumn] = useState(() => readRevenueColumn(profile));
  const [revenuePerKpi, setRevenuePerKpi] = useState<number | null>(() => readRevenuePerKpi());
  const hasProfile = Boolean(profile);
  const hasRevenueChoice = kpiType === "revenue" ? Boolean(revenueColumn) : revenuePerKpi !== null && revenuePerKpi > 0;
  const canContinue = hasProfile && Boolean(kpiColumn) && hasRevenueChoice;

  const handleKpiChange = (event: ChangeEvent<HTMLSelectElement>) => {
    setKpiColumn(event.target.value);
    window.localStorage.setItem(kpiColumnStorageKey, event.target.value);
  };

  const handleKpiTypeChange = (event: ChangeEvent<HTMLSelectElement>) => {
    const next = event.target.value === "revenue" ? "revenue" : "non_revenue";
    setKpiType(next);
    window.localStorage.setItem(kpiTypeStorageKey, next);
  };

  const handleRevenueColumnChange = (event: ChangeEvent<HTMLSelectElement>) => {
    setRevenueColumn(event.target.value);
    window.localStorage.setItem(revenueColumnStorageKey, event.target.value);
  };

  const handleRevenuePerKpiChange = (event: ChangeEvent<HTMLInputElement>) => {
    const next = Number(event.target.value);
    setRevenuePerKpi(Number.isFinite(next) && next > 0 ? next : null);
    if (Number.isFinite(next) && next > 0) {
      window.localStorage.setItem(revenuePerKpiStorageKey, String(next));
    } else {
      window.localStorage.removeItem(revenuePerKpiStorageKey);
    }
  };

  if (!profile) {
    return (
      <WorkflowScaffold
        title="KPI & Revenue Setup"
        summary="Configure how your KPI will be converted into revenue-equivalent ROI."
        primaryActionDisabled
        nextHelperText="Upload and profile a CSV first."
      >
        <section className="content-panel">
          <div className="section-title-row">
            <div>
              <span className="eyebrow">Dataset required</span>
              <h3>Upload and profile a CSV first</h3>
              <p>KPI selection and revenue setup stay locked until a valid dataset profile exists.</p>
            </div>
          </div>
        </section>
      </WorkflowScaffold>
    );
  }

  return (
    <WorkflowScaffold
      title="KPI & Revenue Setup"
      summary="Configure how your KPI will be converted into revenue-equivalent ROI."
      primaryActionDisabled={!canContinue}
      nextHelperText={canContinue ? "Prior Grid Setup" : "Complete KPI and revenue setup to continue."}
    >
      <section className="kpi-summary-grid" aria-label="KPI revenue setup summary">
        <KpiSummaryCard icon="table" label="Dataset" value={profile.filename} note={`${profile.row_count} profiled rows`} />
        <KpiSummaryCard icon="tag" label="KPI Column" value={kpiColumn || "Not selected"} note={`${profile.detected.kpi_candidates.length} candidates detected`} />
        <KpiSummaryCard icon="dollar" label="Revenue Input" value={kpiType === "revenue" ? revenueColumn || "Not selected" : revenuePerKpi ? String(revenuePerKpi) : "Required"} note={kpiType === "revenue" ? "Direct revenue KPI" : "Revenue per KPI unit"} />
        <KpiSummaryCard icon="target" label="ROI Label" value={hasRevenueChoice ? "Revenue-equivalent ROI" : "Pending"} note="Used in config preview and run outputs" />
      </section>

      <section className="content-panel kpi-conversion-card">
        <div className="product-section-heading">
          <h3>Detected Columns</h3>
          <p>Select from the columns profiled in the uploaded CSV.</p>
        </div>

        <div className="prior-range-fields">
          <label>
            <span>KPI column</span>
            <select value={kpiColumn} onChange={handleKpiChange}>
              <option value="">Select KPI</option>
              {profile.detected.kpi_candidates.map((column) => (
                <option key={column} value={column}>{column}</option>
              ))}
            </select>
          </label>
          <label>
            <span>KPI type</span>
            <select value={kpiType} onChange={handleKpiTypeChange}>
              <option value="non_revenue">Non-revenue KPI</option>
              <option value="revenue">Revenue KPI</option>
            </select>
          </label>
          {kpiType === "revenue" ? (
            <label>
              <span>Revenue column</span>
              <select value={revenueColumn} onChange={handleRevenueColumnChange}>
                <option value="">Select revenue column</option>
                {profile.detected.revenue_candidates.map((column) => (
                  <option key={column} value={column}>{column}</option>
                ))}
              </select>
            </label>
          ) : (
            <label>
              <span>Revenue per KPI</span>
              <input min="0" step="0.1" type="number" value={revenuePerKpi ?? ""} onChange={handleRevenuePerKpiChange} />
            </label>
          )}
        </div>
      </section>
    </WorkflowScaffold>
  );
}
