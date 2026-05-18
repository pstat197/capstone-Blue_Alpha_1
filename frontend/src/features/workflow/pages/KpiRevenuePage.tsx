import type { ChangeEvent } from "react";
import { useEffect, useMemo, useState } from "react";
import { WorkflowScaffold } from "../components/WorkflowScaffold";
import { revenuePerKpiStorageKey } from "../data/mockWorkflow";
import {
  detectedChannels,
  kpiColumnStorageKey,
  kpiTypeStorageKey,
  readActiveProfile,
  readKpiColumn,
  readRevenueColumn,
  readRevenuePerKpi,
  readRoiMode,
  revenueAssumptionSavedStorageKey,
  revenueColumnStorageKey,
  roiModeStorageKey,
} from "../data/workflowState";

type ProductIcon = "table" | "tag" | "dollar" | "target" | "chart" | "info" | "light" | "shield";

type SummaryItem = {
  icon: ProductIcon;
  tone?: "blue" | "green" | "amber" | "purple";
  label: string;
  value: string;
};

type ChecklistItem = {
  icon: ProductIcon;
  title: string;
  copy: string;
};

function IconBadge({ icon, tone = "blue" }: { icon: ProductIcon; tone?: SummaryItem["tone"] }) {
  return <span className={`product-icon product-icon--${icon} product-icon--tone-${tone}`} aria-hidden="true" />;
}

function SummaryStrip({ items }: { items: SummaryItem[] }) {
  return (
    <section className="kpi-setup-summary-strip" aria-label="KPI revenue setup summary">
      {items.map((item) => (
        <article className="kpi-setup-summary-item" key={item.label}>
          <IconBadge icon={item.icon} tone={item.tone} />
          <div>
            <span>{item.label}</span>
            <strong>{item.value}</strong>
          </div>
        </article>
      ))}
    </section>
  );
}

function StatusPill({ children, tone }: { children: string; tone: "ready" | "review" }) {
  return <span className={`kpi-status-pill kpi-status-pill--${tone}`}>{children}</span>;
}

function Checklist({ items }: { items: ChecklistItem[] }) {
  return (
    <div className="kpi-setup-checklist">
      {items.map((item) => (
        <article className="kpi-setup-check-row" key={item.title}>
          <IconBadge icon={item.icon} tone="green" />
          <div>
            <strong>{item.title}</strong>
            <p>{item.copy}</p>
          </div>
        </article>
      ))}
    </div>
  );
}

function FlowStep({
  icon,
  label,
  value,
  note,
  tone,
}: {
  icon: ProductIcon;
  label: string;
  value: string;
  note: string;
  tone?: SummaryItem["tone"];
}) {
  return (
    <article className="kpi-flow-step">
      <IconBadge icon={icon} tone={tone} />
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <p>{note}</p>
      </div>
    </article>
  );
}

function parseRevenuePerKpi(value: string) {
  const parsed = Number(value.replace(/[$,\s]/g, ""));
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

export function KpiRevenuePage() {
  const profile = useMemo(() => readActiveProfile(), []);
  const channels = useMemo(() => detectedChannels(profile), [profile]);
  const [kpiColumn, setKpiColumn] = useState(() => readKpiColumn(profile));
  const [revenueColumn, setRevenueColumn] = useState(() => readRevenueColumn(profile));
  const [roiMode, setRoiMode] = useState(() => readRoiMode(profile));
  const storedRevenuePerKpi = readRevenuePerKpi();
  const [revenuePerKpiInput, setRevenuePerKpiInput] = useState(() => (storedRevenuePerKpi ? String(storedRevenuePerKpi) : ""));
  const [savedRevenuePerKpi, setSavedRevenuePerKpi] = useState<number | null>(() => storedRevenuePerKpi);
  const [showRevenueMapping, setShowRevenueMapping] = useState(false);
  const [showKpiMapping, setShowKpiMapping] = useState(false);
  const hasProfile = Boolean(profile);
  const hasDetectedRevenueColumn = Boolean(profile?.detected.revenue_candidates.length);
  const revenueCandidates = profile?.detected.revenue_candidates ?? [];
  const isDirectRevenueMode = hasDetectedRevenueColumn && roiMode === "direct_revenue_column";
  const validRevenuePerKpi = parseRevenuePerKpi(revenuePerKpiInput);
  const canContinue = hasProfile && Boolean(kpiColumn) && (isDirectRevenueMode ? Boolean(revenueColumn) : Boolean(savedRevenuePerKpi));
  const channelsSummary = `${channels.length} ${channels.length === 1 ? "channel" : "channels"}`;
  const revenueColumnSummary = isDirectRevenueMode ? revenueColumn || revenueCandidates[0] || "missing" : "missing";

  useEffect(() => {
    if (!profile) {
      return;
    }

    if (hasDetectedRevenueColumn) {
      const nextRevenueColumn = revenueColumn || revenueCandidates[0] || "";
      setRoiMode("direct_revenue_column");
      setRevenueColumn(nextRevenueColumn);
      window.localStorage.setItem(roiModeStorageKey, "direct_revenue_column");
      window.localStorage.setItem(kpiTypeStorageKey, "revenue");
      window.localStorage.removeItem(revenueAssumptionSavedStorageKey);
      if (kpiColumn) {
        window.localStorage.setItem(kpiColumnStorageKey, kpiColumn);
      }
      if (nextRevenueColumn) {
        window.localStorage.setItem(revenueColumnStorageKey, nextRevenueColumn);
      }
      return;
    }

    setRoiMode("revenue_per_kpi_assumption");
    window.localStorage.setItem(roiModeStorageKey, "revenue_per_kpi_assumption");
    window.localStorage.setItem(kpiTypeStorageKey, "non_revenue");
    if (kpiColumn) {
      window.localStorage.setItem(kpiColumnStorageKey, kpiColumn);
    }
  }, [hasDetectedRevenueColumn, kpiColumn, profile, revenueCandidates, revenueColumn]);

  const handleKpiChange = (event: ChangeEvent<HTMLSelectElement>) => {
    setKpiColumn(event.target.value);
    window.localStorage.setItem(kpiColumnStorageKey, event.target.value);
  };

  const handleRevenueColumnChange = (event: ChangeEvent<HTMLSelectElement>) => {
    setRevenueColumn(event.target.value);
    window.localStorage.setItem(revenueColumnStorageKey, event.target.value);
  };

  const handleRevenuePerKpiChange = (event: ChangeEvent<HTMLInputElement>) => {
    setRevenuePerKpiInput(event.target.value);
    setSavedRevenuePerKpi(null);
    window.localStorage.removeItem(revenuePerKpiStorageKey);
    window.localStorage.removeItem(revenueAssumptionSavedStorageKey);
  };

  const saveAssumption = (value: number | null = validRevenuePerKpi) => {
    if (!value) {
      return;
    }
    setRevenuePerKpiInput(String(value));
    setSavedRevenuePerKpi(value);
    window.localStorage.setItem(revenuePerKpiStorageKey, String(value));
    window.localStorage.setItem(revenueAssumptionSavedStorageKey, "true");
    window.localStorage.setItem(roiModeStorageKey, "revenue_per_kpi_assumption");
    window.localStorage.setItem(kpiTypeStorageKey, "non_revenue");
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

  const summaryItems: SummaryItem[] = [
    { icon: "table", label: "Dataset", value: profile.filename },
    { icon: "target", label: "KPI", value: kpiColumn || "Not selected" },
    {
      icon: "dollar",
      tone: isDirectRevenueMode ? "green" : "amber",
      label: "Revenue column",
      value: revenueColumnSummary,
    },
    { icon: "chart", tone: "purple", label: "Channels detected", value: channelsSummary },
  ];

  if (isDirectRevenueMode) {
    return (
      <WorkflowScaffold
        title="KPI & Revenue Setup"
        summary="Revenue was detected in your data. Review the mapping below—ROI will be calculated directly."
        primaryActionDisabled={!canContinue}
        primaryActionLabel="Continue to Prior Grid Setup"
        nextHelperText={canContinue ? "Prior Grid Setup" : "Select a revenue column to continue"}
      >
        <SummaryStrip items={summaryItems} />

        <section className="kpi-setup-layout" aria-label="Direct ROI configuration">
          <article className="content-panel kpi-setup-card">
            <div className="kpi-setup-card-heading">
              <h3>Direct ROI Configuration</h3>
              <StatusPill tone="ready">Ready</StatusPill>
            </div>
            <p>Your columns are mapped and ROI will be calculated directly.</p>

            <div className="kpi-direct-flow">
              <FlowStep icon="target" label="KPI column" value={kpiColumn || "Not selected"} note="Used as the denominator" />
              <span className="kpi-flow-arrow" aria-hidden="true" />
              <FlowStep icon="dollar" label="Revenue column" value={revenueColumn || "Not selected"} note="Used as the numerator" tone="green" />
              <span className="kpi-flow-arrow" aria-hidden="true" />
              <FlowStep icon="chart" label="Output" value="ROI" note="Calculated as revenue / KPI" />
            </div>

            <div className="kpi-support-message kpi-support-message--success">
              <IconBadge icon="info" tone="green" />
              <p>ROI will be calculated directly from your detected revenue column—no assumptions required.</p>
            </div>

            {showRevenueMapping ? (
              <label className="kpi-inline-field">
                <span>Revenue column</span>
                <select value={revenueColumn} onChange={handleRevenueColumnChange}>
                  {revenueCandidates.map((column) => (
                    <option key={column} value={column}>{column}</option>
                  ))}
                </select>
              </label>
            ) : null}

            <div className="kpi-card-actions">
              <button className="kpi-link-button" onClick={() => setShowRevenueMapping((current) => !current)} type="button">
                Change revenue mapping
              </button>
            </div>
          </article>

          <article className="content-panel kpi-explainer-card">
            <h3>Why no assumption is needed</h3>
            <p>We detected a revenue column in your dataset, so ROI can be computed directly for each time period.</p>
            <Checklist
              items={[
                { icon: "info", title: "Revenue detected", copy: `Your data includes a revenue column (${revenueColumn || "revenue"}).` },
                { icon: "chart", title: "Direct ROI mode", copy: "ROI is calculated as revenue ÷ KPI automatically." },
                { icon: "light", title: "Fewer things to configure", copy: "No revenue_per_kpi value needed. Move forward faster." },
              ]}
            />
          </article>
        </section>
      </WorkflowScaffold>
    );
  }

  return (
    <WorkflowScaffold
      title="KPI & Revenue Setup"
      summary="No revenue column was detected in your data. Configure a revenue-per-KPI assumption to enable ROI calculations."
      primaryActionDisabled={!canContinue}
      primaryActionLabel="Continue to Prior Grid Setup"
      nextHelperText={canContinue ? "Prior Grid Setup" : "Save your assumption to continue"}
    >
      <SummaryStrip items={summaryItems} />

      <section className="kpi-setup-layout" aria-label="Revenue-equivalent ROI assumption">
        <article className="content-panel kpi-setup-card">
          <div className="kpi-setup-card-heading">
            <h3>Revenue-equivalent ROI Assumption</h3>
            <StatusPill tone="review">Needs review</StatusPill>
          </div>
          <p>Enter the business-defined revenue value for one unit of the selected KPI.</p>

          <label className="kpi-assumption-field">
            <span>
              Revenue per KPI unit
              <small>USD per KPI</small>
            </span>
            <input
              inputMode="decimal"
              onChange={handleRevenuePerKpiChange}
              type="text"
              value={revenuePerKpiInput}
            />
          </label>
          <p className="kpi-field-helper">Used to convert {kpiColumn || "the selected KPI"} into revenue-equivalent ROI for prior setup and outputs.</p>

          {showKpiMapping ? (
            <label className="kpi-inline-field">
              <span>KPI column</span>
              <select value={kpiColumn} onChange={handleKpiChange}>
                {profile.detected.kpi_candidates.map((column) => (
                  <option key={column} value={column}>{column}</option>
                ))}
              </select>
            </label>
          ) : null}

          <div className="kpi-support-message kpi-support-message--warning">
            <IconBadge icon="info" tone="amber" />
            <p>This does not change your raw dataset. It only enables ROI-style outputs for a non-revenue KPI.</p>
          </div>

          <div className="kpi-card-actions kpi-card-actions--split">
            <button className="kpi-link-button" onClick={() => setShowKpiMapping((current) => !current)} type="button">
              Edit KPI mapping
            </button>
            <div>
              <button className="kpi-save-button" disabled={!validRevenuePerKpi} onClick={() => saveAssumption()} type="button">
                Save assumption
              </button>
            </div>
          </div>
        </article>

        <article className="content-panel kpi-explainer-card">
          <h3>Why this assumption is needed</h3>
          <p>Because no revenue column was detected in your dataset, the model needs a business-defined value per KPI unit before prior grid setup.</p>
          <Checklist
            items={[
              { icon: "dollar", title: "Revenue-equivalent ROI", copy: "Enables ROI-style outputs by converting your KPI into revenue-equivalent value." },
              { icon: "chart", title: "Model-ready conversion", copy: "Allows the model to apply priors and compute ROI during prior grid setup." },
              { icon: "shield", title: "You stay in control", copy: "You define the value based on your business knowledge and can update it anytime." },
            ]}
          />
        </article>
      </section>
    </WorkflowScaffold>
  );
}
