import type { ChangeEvent, DragEvent } from "react";
import { useMemo, useRef, useState } from "react";
import { FileSpreadsheet } from "lucide-react";
import { createUpload, getUploadPreview, getUploadProfile } from "../../../api/uploads";
import type { ChannelDiagnostic, CsvPreview, CsvProfile } from "../../../api/types";
import { StatusBadge } from "../components/StatusBadge";
import { WorkflowScaffold } from "../components/WorkflowScaffold";
import {
  clearActiveProfile,
  clearDatasetSelections,
  readActiveProfile,
  writeActiveProfile,
} from "../data/workflowState";

type ColumnRow = {
  name: string;
  role: string;
  status: "valid" | "warning" | "missing";
  detail?: string;
  tag?: string;
  tone?: "required" | "helper" | "optional" | "control";
};
type ColumnGroups = {
  time: ColumnRow[];
  kpi: ColumnRow[];
  media: ColumnRow[];
  helpers: ColumnRow[];
  optional: ColumnRow[];
};

function FieldCard({ row, compact = false }: { row: ColumnRow; compact?: boolean }) {
  const showStatus = row.tone === "required" || row.tone === "helper";
  return (
    <article className={`dataset-field-card dataset-field-card--${row.tone ?? "required"}${compact ? " dataset-field-card--compact" : ""}`}>
      {showStatus ? <StatusBadge status={row.status} /> : null}
      <div>
        <div className="dataset-field-title-row">
          <strong>{row.name}</strong>
          {row.tag ? <span>{row.tag}</span> : null}
        </div>
        <p>{row.role}</p>
        {row.detail ? <small>{row.detail}</small> : null}
      </div>
    </article>
  );
}

function EmptyProfileCard({ copy }: { copy: string }) {
  return (
    <article className="dataset-field-card dataset-field-card--empty">
      <div>
        <strong>Not detected</strong>
        <p>{copy}</p>
      </div>
    </article>
  );
}

function DatasetProfileLayout({ profile, groups, onPreview }: { profile: CsvProfile; groups: ColumnGroups; onPreview: () => void }) {
  const helperName = groups.helpers[0]?.name ?? "the helper field";
  return (
    <section className="content-panel dataset-profile-panel dataset-profile-panel--redesigned">
      <div className="section-title-row dataset-profile-title-row">
        <div>
          <h3>Dataset Profile</h3>
          <p>We have profiled your file and mapped the key fields below.</p>
        </div>
        <button className="preview-data-button" type="button" onClick={onPreview}>
          Preview data
        </button>
      </div>

      <section className="dataset-required-grid" aria-label="Required model fields">
        <div className="dataset-required-card">
          <h4>1. Time</h4>
          {groups.time[0] ? <FieldCard row={groups.time[0]} /> : <EmptyProfileCard copy="A date/time field is required." />}
        </div>
        <div className="dataset-required-card">
          <h4>2. KPI</h4>
          {groups.kpi[0] ? <FieldCard row={groups.kpi[0]} /> : <EmptyProfileCard copy="A KPI field is required." />}
        </div>
        <div className="dataset-required-card dataset-required-card--media">
          <div className="dataset-profile-section-heading">
            <h4>3. Paid media spend columns</h4>
            <span>{groups.media.length} {groups.media.length === 1 ? "channel" : "channels"}</span>
          </div>
          <div className="dataset-media-grid">
            {groups.media.map((row) => <FieldCard compact key={row.name} row={row} />)}
          </div>
        </div>
      </section>

      <section className="dataset-helper-section" aria-label="Revenue and helper inputs">
        <div className="dataset-section-intro dataset-section-intro--helper">
          <div>
            <h4>Revenue & helper inputs</h4>
            <p>Helper fields that enhance analysis and enable additional outputs.</p>
          </div>
        </div>
        <div className="dataset-helper-content">
          {groups.helpers.length ? (
            groups.helpers.map((row) => <FieldCard key={row.name} row={row} />)
          ) : (
            <EmptyProfileCard copy="No revenue-per-KPI helper was detected." />
          )}
          <div className="dataset-helper-note">
            <p>This field helps convert {profile.detected.kpi_candidates[0] ?? "the KPI"} to revenue-equivalent values and compute ROI in revenue terms.</p>
            <span>{helperName} can be reviewed in the KPI & Revenue step.</span>
          </div>
        </div>
      </section>

      <section className="dataset-optional-section" aria-label="Additional optional fields">
        <div className="dataset-section-intro">
          <div>
            <h4>Additional optional fields</h4>
            <p>Optional fields that may be used for diagnostics and controls.</p>
          </div>
        </div>
        <div className="dataset-optional-grid">
          {groups.optional.map((row) => <FieldCard compact key={row.name} row={row} />)}
        </div>
      </section>

      <footer className="dataset-profile-legend" aria-label="Dataset profile legend">
        <span><i className="dataset-legend-dot dataset-legend-dot--required" /> Required detected</span>
        <span><i className="dataset-legend-dot dataset-legend-dot--helper" /> Helper input</span>
        <span><i className="dataset-legend-dot dataset-legend-dot--optional" /> Optional field</span>
        <span><i className="dataset-legend-dot dataset-legend-dot--control" /> Potential control input</span>
        <p>Fields are automatically profiled. You can review or adjust mappings in the next step.</p>
      </footer>
    </section>
  );
}

function columnDetail(profile: CsvProfile, name: string): string {
  const column = profile.columns.find((item) => item.name === name);
  if (!column) {
    return "";
  }
  const parts = [`${Math.round(column.null_rate * 100)}% null`];
  if (typeof column.nonzero_rate === "number") {
    parts.push(`${Math.round(column.nonzero_rate * 100)}% nonzero`);
  }
  if (typeof column.total_value === "number") {
    parts.push(`total = ${formatTotal(column.total_value)}`);
  }
  return parts.join(" · ");
}

function helperDetail(profile: CsvProfile, name: string): string {
  const column = profile.columns.find((item) => item.name === name);
  if (!column) {
    return "";
  }
  const parts = [`${Math.round(column.null_rate * 100)}% null`];
  if (typeof column.nonzero_rate === "number") {
    parts.push(`${Math.round(column.nonzero_rate * 100)}% nonzero`);
  }
  if (typeof column.total_value === "number" && profile.row_count > 0) {
    parts.push(`total average = ${formatTotal(column.total_value / profile.row_count)}`);
  }
  return parts.join(" · ");
}

function conciseColumnDetail(profile: CsvProfile, name: string): string {
  const column = profile.columns.find((item) => item.name === name);
  if (!column) {
    return "";
  }
  const parts = [`${Math.round(column.null_rate * 100)}% null`];
  if (typeof column.nonzero_rate === "number") {
    parts.push(`${Math.round(column.nonzero_rate * 100)}% nonzero`);
  }
  if (typeof column.total_value === "number") {
    parts.push(`total = ${formatTotal(column.total_value)}`);
  }
  return parts.join(" · ");
}

function formatTotal(value: number): string {
  if (Math.abs(value) >= 1000) {
    return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function formatPercent(value: number | null | undefined): string {
  if (typeof value !== "number") {
    return "n/a";
  }
  return `${Math.round(value * 100)}%`;
}

function formatDateRange(profile: CsvProfile): string {
  const dateProfile = profile.date_profile;
  if (!dateProfile || dateProfile.status === "missing") {
    return "Date range unavailable";
  }
  if (!dateProfile.date_min || !dateProfile.date_max) {
    return "Could not parse date range";
  }
  return `${dateProfile.date_min.slice(0, 7)} → ${dateProfile.date_max.slice(0, 7)}`;
}

function channelLabel(status: ChannelDiagnostic["status"]): string {
  if (status === "active_paid_media") {
    return "Active paid media";
  }
  if (status === "spend_as_media_fallback") {
    return "Spend-as-media fallback";
  }
  if (status === "inactive_all_zero") {
    return "Inactive";
  }
  return "Not eligible";
}

function spendDetail(diagnostic: ChannelDiagnostic): string {
  return `${formatPercent(diagnostic.spend_null_rate)} null · ${formatPercent(diagnostic.spend_nonzero_rate)} nonzero · total = ${formatTotal(diagnostic.spend_total ?? 0)}`;
}

function normalizedColumnName(name: string): string {
  return name.toLowerCase().replace(/[-\s]+/g, "_");
}

function isControlLikeColumn(name: string): boolean {
  const normalized = normalizedColumnName(name);
  return ["_control", "control", "competitor", "sentiment", "promo"].some((token) => normalized.includes(token));
}

function isRevenuePerKpiColumnName(name: string): boolean {
  const normalized = normalizedColumnName(name);
  if (isControlLikeColumn(name)) {
    return false;
  }
  return (
    normalized.startsWith("revenue_per_") ||
    normalized.startsWith("rev_per_") ||
    normalized.startsWith("value_per_") ||
    normalized.startsWith("dollars_per_") ||
    normalized.startsWith("dollar_per_") ||
    normalized.includes("_revenue_per_")
  );
}

function isDirectRevenueColumnName(name: string): boolean {
  const normalized = normalizedColumnName(name);
  if (isControlLikeColumn(name) || isRevenuePerKpiColumnName(name)) {
    return false;
  }
  return ["revenue", "sales", "total_revenue", "gross_revenue", "net_revenue", "gmv", "income", "turnover"].includes(normalized);
}

function uniqueNames(names: string[]): string[] {
  return Array.from(new Set(names.filter(Boolean)));
}

function effectiveRevenueClassification(profile: CsvProfile) {
  const detectedRevenue = profile.detected.revenue_candidates ?? [];
  const detectedHelpers = profile.detected.revenue_per_kpi_candidates ?? [];
  return {
    helpers: uniqueNames([
      ...detectedHelpers,
      ...detectedRevenue.filter(isRevenuePerKpiColumnName),
    ]).filter((name) => !isControlLikeColumn(name)),
    directRevenue: uniqueNames(detectedRevenue).filter(isDirectRevenueColumnName),
    controls: uniqueNames([
      ...(profile.detected.control_candidates ?? []),
      ...detectedRevenue.filter(isControlLikeColumn),
      ...detectedHelpers.filter(isControlLikeColumn),
      ...profile.columns.map((column) => column.name).filter(isControlLikeColumn),
    ]),
  };
}

function displayValidationBadges(profile: CsvProfile) {
  const revenue = effectiveRevenueClassification(profile);
  return profile.validation_badges.map((badge) => {
    const lower = badge.label.toLowerCase();
    if (!lower.includes("revenue")) {
      return badge;
    }
    if (revenue.directRevenue.length) {
      return { ...badge, status: "valid", label: "Revenue column detected" };
    }
    if (revenue.helpers.length) {
      return { ...badge, status: "valid", label: "Revenue-per-KPI helper detected" };
    }
    return { ...badge, status: "warning", label: "Revenue column not detected" };
  });
}

function profileToColumnGroups(profile: CsvProfile): ColumnGroups {
  const diagnosticsBySpendColumn = new Map((profile.channel_diagnostics ?? []).map((item) => [item.spend_column, item]));
  const revenue = effectiveRevenueClassification(profile);
  const knownColumns = new Set<string>();
  [
    ...profile.detected.time_candidates,
    ...profile.detected.kpi_candidates,
    ...revenue.directRevenue,
    ...revenue.helpers,
    ...revenue.controls,
    ...profile.detected.geo_candidates,
    ...profile.detected.population_candidates,
    ...profile.detected.spend_channel_candidates.map((item) => item.column),
    ...profile.detected.media_activity_candidates.map((item) => item.column),
  ].forEach((name) => knownColumns.add(name));

  const extraOptionalRows = profile.columns
    .filter((column) => !knownColumns.has(column.name))
    .map((column) => ({
      name: column.name,
      role: "Optional field",
      status: "valid" as const,
      detail: conciseColumnDetail(profile, column.name),
      tag: "Optional",
      tone: "optional" as const,
    }));

  return {
    time: profile.detected.time_candidates.map((name) => ({
      name,
      role: "Date/time candidate",
      status: profile.date_profile?.status === "warning" ? "warning" : "valid",
      detail: columnDetail(profile, name),
      tone: "required" as const,
    })),
    kpi: profile.detected.kpi_candidates.map((name) => ({
      name,
      role: "KPI candidate",
      status: "valid",
      detail: columnDetail(profile, name),
      tone: "required" as const,
    })),
    media: profile.detected.spend_channel_candidates.filter((item) => {
      const diagnostic = diagnosticsBySpendColumn.get(item.column);
      return diagnostic?.include_in_model ?? true;
    }).map((item) => {
      const diagnostic = diagnosticsBySpendColumn.get(item.column);
      return {
        name: item.column,
        role: diagnostic ? channelLabel(diagnostic.status) : `${item.channel.toUpperCase()} spend`,
        status: diagnostic?.severity ?? "valid",
        detail: diagnostic ? spendDetail(diagnostic) : conciseColumnDetail(profile, item.column),
        tone: "required" as const,
      };
    }),
    helpers: [
      ...revenue.helpers.map((name) => ({
        name,
        role: "Revenue-per-KPI helper",
        status: "valid" as const,
        detail: helperDetail(profile, name),
        tag: "Revenue-per-KPI helper",
        tone: "helper" as const,
      })),
      ...revenue.directRevenue.map((name) => ({
        name,
        role: "Direct revenue input",
        status: "valid" as const,
        detail: conciseColumnDetail(profile, name),
        tag: "Direct revenue",
        tone: "helper" as const,
      })),
    ],
    optional: [
      ...profile.detected.media_activity_candidates.map((item) => ({
        name: item.column,
        role: "Media activity",
        status: "valid" as const,
        tag: "Optional",
        tone: "optional" as const,
      })),
      ...revenue.controls.map((name) => ({
        name,
        role: "Not used unless mapped",
        status: "valid" as const,
        tag: "Potential control",
        tone: "control" as const,
      })),
      ...extraOptionalRows,
    ],
  };
}

function validationStatusClass(status: string) {
  if (status === "error") {
    return "missing";
  }
  if (status === "info") {
    return "locked";
  }
  return status as "valid" | "warning" | "missing" | "locked";
}

function validationDetail(label: string, profile?: CsvProfile | null) {
  const lower = label.toLowerCase();
  if (lower.includes("date") || lower.includes("time")) {
    return "Required for time-series indexing";
  }
  if (lower.includes("revenue-per-kpi")) {
    const helper = profile?.detected.revenue_per_kpi_candidates?.[0] ?? "This helper";
    return `${helper} can be used for revenue-equivalent ROI.`;
  }
  if (lower.includes("kpi")) {
    return "Choose one on the next step";
  }
  if (lower.includes("inactive")) {
    return "Excluded from model by default";
  }
  if (lower.includes("active channel") || lower.includes("spend")) {
    return "Used to detect channel priors";
  }
  if (lower.includes("activity")) {
    return "Recommended for Meridian media inputs";
  }
  if (lower.includes("revenue")) {
    return lower.includes("per-kpi")
      ? "Used to compute revenue-equivalent ROI for a non-revenue KPI."
      : "You will choose revenue-per-KPI or non-revenue prior handling on the next step.";
  }
  return "";
}

function compactValidationLabel(label: string) {
  if (label.includes(";")) {
    return label.split(";")[0];
  }
  return label;
}

function isGeoPopulationLabel(label: string) {
  const lower = label.toLowerCase();
  return lower.includes("geo") || lower.includes("population");
}

function hasRequiredUploadFields(profile: CsvProfile | null) {
  if (!profile) {
    return false;
  }
  return profile.validation_badges.every((badge) => badge.status !== "error" || isGeoPopulationLabel(badge.label));
}

const emptyStateReassurances = [
  "We detect time, KPI, media, and spend columns",
  "We keep your previous dataset active if replacement fails",
  "You can remove or replace files later",
];

export function NewAnalysisUploadPage() {
  const [profile, setProfile] = useState<CsvProfile | null>(() => readActiveProfile());
  const [uploadStatus, setUploadStatus] = useState<"idle" | "uploading" | "api" | "error">("idle");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [replacementWarning, setReplacementWarning] = useState<string | null>(null);
  const [isRemoveConfirmOpen, setIsRemoveConfirmOpen] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [preview, setPreview] = useState<CsvPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const chooseInputRef = useRef<HTMLInputElement | null>(null);
  const replaceInputRef = useRef<HTMLInputElement | null>(null);

  const columnGroups = useMemo<ColumnGroups>(() => {
    if (profile) {
      return profileToColumnGroups(profile);
    }
    return {
      time: [],
      kpi: [],
      media: [],
      helpers: [],
      optional: [],
    };
  }, [profile]);

  const validationBadges = (profile ? displayValidationBadges(profile) : []).filter((badge) => !isGeoPopulationLabel(badge.label));

  const channelDiagnostics = profile?.channel_diagnostics ?? [];
  const activeChannels = channelDiagnostics.filter((item) => item.include_in_model).length;
  const excludedChannels = channelDiagnostics.filter((item) => !item.include_in_model).length;
  const setupWarnings = validationBadges.filter((badge) => badge.status === "warning").length;

  const profileSummary = {
    filename: profile?.filename ?? "",
    rows: profile?.row_count ?? 0,
    channels: channelDiagnostics.length || profile?.detected.spend_channel_candidates.length || 0,
    activeChannels,
    excludedChannels,
    kpi: profile?.detected.kpi_candidates[0] ?? "Not detected",
    dateRange: profile ? formatDateRange(profile) : "",
  };

  const canContinue = hasRequiredUploadFields(profile);
  const hasActiveProfile = Boolean(profile);

  const handleSelectedFile = (file?: File, mode: "new" | "replace" = profile ? "replace" : "new") => {
    if (!file) {
      return;
    }

    setUploadStatus("uploading");
    setUploadError(null);
    setReplacementWarning(null);
    createUpload(file)
      .then((upload) => getUploadProfile(upload.upload_id))
      .then((apiProfile) => {
        clearDatasetSelections();
        writeActiveProfile(apiProfile);
        setProfile(apiProfile);
        setUploadStatus("api");
        setUploadError(null);
        setReplacementWarning(null);
        setPreview(null);
        setPreviewError(null);
      })
      .catch((error: unknown) => {
        if (mode === "replace" && profile) {
          setUploadStatus("api");
          setReplacementWarning(`We could not profile the replacement file, so your previous dataset remains active. ${error instanceof Error ? error.message : ""}`);
          return;
        }
        setUploadStatus("error");
        setUploadError(error instanceof Error ? error.message : "We could not profile that file.");
      });
  };

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    handleSelectedFile(event.currentTarget.files?.[0]);
    event.currentTarget.value = "";
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
    handleSelectedFile(event.dataTransfer.files?.[0]);
  };

  const handleOpenPreview = () => {
    if (!profile) {
      return;
    }

    setIsPreviewOpen(true);
    setPreviewError(null);

    getUploadPreview(profile.upload_id, 10)
      .then(setPreview)
      .catch(() => {
        setPreview(null);
        setPreviewError("Unable to load the data preview. Please try again after selecting a CSV.");
      });
  };

  const handleRemoveFile = () => {
    setProfile(null);
    clearActiveProfile();
    setUploadStatus("idle");
    setUploadError(null);
    setReplacementWarning(null);
    setPreview(null);
    setPreviewError(null);
    setIsPreviewOpen(false);
    setIsRemoveConfirmOpen(false);
  };

  const previewColumns = preview?.columns ?? [];
  const previewRows = preview?.rows ?? [];

  return (
    <WorkflowScaffold
      title="Upload / Data Detection"
      summary="Upload your marketing dataset to begin a prior-sensitivity audit."
      primaryActionDisabled={!canContinue}
      nextHelperText={canContinue ? "KPI & Revenue Setup" : "Upload a valid CSV to continue."}
    >
      <section className={profile ? "upload-onboarding-grid upload-onboarding-grid--profile" : "upload-onboarding-grid"}>
        <div className="upload-main-stack">
          {!hasActiveProfile ? (
            <div className="content-panel upload-card upload-empty-card">
              <div
                className={isDragging ? "upload-drop-target upload-drop-target--empty upload-drop-target--dragging" : "upload-drop-target upload-drop-target--empty"}
                onDragOver={(event) => {
                  event.preventDefault();
                  setIsDragging(true);
                }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={handleDrop}
              >
                <div className="upload-cloud" aria-hidden="true" />
                <h3>Drag & drop your CSV file here</h3>
                <p>or choose a file from your computer</p>
                <div className="empty-upload-actions">
                  <label className="file-picker file-picker--primary">
                    <span>{uploadStatus === "uploading" ? "Profiling..." : "Choose CSV"}</span>
                    <input ref={chooseInputRef} type="file" accept=".csv,text/csv" onChange={handleFileChange} />
                  </label>
                </div>
              </div>
              <div className="upload-empty-helper-row" aria-label="Upload requirements">
                <span>Accepted format: .csv</span>
                <span>One file only</span>
                <span>Your file stays in this workspace</span>
              </div>
              <div className="upload-empty-reassurance-grid">
                {emptyStateReassurances.map((item, index) => (
                  <div className="upload-empty-reassurance-card" key={item}>
                    <span aria-hidden="true">{index + 1}</span>
                    <strong>{item}</strong>
                  </div>
                ))}
              </div>
              {uploadError ? <p className="upload-fallback-note">{uploadError}</p> : null}
            </div>
          ) : null}

          {profile ? (
            <div className="dataset-summary-card">
              <h3 className="dataset-summary-section-label">Dataset</h3>
              <div className="dataset-file-row">
                <div className="dataset-file-icon" aria-hidden="true">
                  <FileSpreadsheet size={24} strokeWidth={2.2} />
                </div>
                <div className="dataset-file-heading">
                  <h3>{profileSummary.filename}</h3>
                  <p>{uploadStatus === "uploading" ? "Profiling replacement..." : "Ready for setup"}</p>
                </div>
                <div className="dataset-file-actions">
                  <button className="replace-file-button" type="button" onClick={() => replaceInputRef.current?.click()}>
                    Replace file
                  </button>
                  <button className="remove-file-button" type="button" onClick={() => setIsRemoveConfirmOpen(true)}>
                    Remove file
                  </button>
                </div>
              </div>
              <input ref={replaceInputRef} id="replace-csv-input" className="visually-hidden" type="file" accept=".csv,text/csv" onChange={handleFileChange} />
              <div className="dataset-summary-divider" aria-hidden="true" />
              <h3 className="dataset-summary-section-label">Overview</h3>
              <div className="dataset-facts">
                <div>
                  <span>Rows</span>
                  <strong>{profileSummary.rows}</strong>
                </div>
                <div>
                  <span>Detected channels</span>
                  <strong>{profileSummary.channels}</strong>
                </div>
                <div>
                  <span>Active paid channels</span>
                  <strong>{profileSummary.activeChannels}</strong>
                </div>
                <div>
                  <span>Excluded channels</span>
                  <strong>{profileSummary.excludedChannels}</strong>
                </div>
                <div>
                  <span>KPI candidate</span>
                  <strong>{profileSummary.kpi}</strong>
                </div>
                <div>
                  <span>Date range</span>
                  <strong>{profileSummary.dateRange}</strong>
                </div>
              </div>
              {replacementWarning ? (
                <div className="replacement-warning" role="status">
                  <p>{replacementWarning}</p>
                  <div>
                    <button className="replace-file-button" type="button" onClick={() => replaceInputRef.current?.click()}>
                      Try another file
                    </button>
                    <button className="keep-current-file-button" type="button" onClick={() => setReplacementWarning(null)}>
                      Keep current file
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>

        {profile ? <div className="upload-side-stack">
          <div className="content-panel validation-card">
            <h3>Required field validation</h3>
            <div className="validation-summary-strip" role="status">
              <strong>{validationBadges.some((badge) => badge.status === "error") ? "Blocking issues found" : "No blocking issues found"}</strong>
              {setupWarnings ? <span>{setupWarnings} setup warning{setupWarnings === 1 ? "" : "s"}</span> : null}
              {excludedChannels ? <span>{excludedChannels} inactive channel{excludedChannels === 1 ? "" : "s"} excluded</span> : null}
            </div>
            <div className="validation-list">
              {validationBadges.map((badge) => (
                <div className="validation-item" key={badge.label}>
                  <StatusBadge status={validationStatusClass(badge.status)} />
                  <div>
                    <strong>{compactValidationLabel(badge.label)}</strong>
                    <span>{validationDetail(badge.label, profile)}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div> : (
          <aside className="upload-empty-side-stack" aria-label="Upload guidance">
            <div className="content-panel upload-empty-side-card">
              <div className="upload-empty-card-heading upload-empty-card-heading--shield">
                <span aria-hidden="true" />
                <h3>What we'll validate</h3>
              </div>
              <ul className="upload-empty-checklist">
                <li>Date/time column</li>
                <li>KPI column</li>
                <li>Matching media + spend pairs</li>
                <li>Revenue or revenue_per_kpi handling</li>
              </ul>
            </div>

            <div className="content-panel upload-empty-side-card">
              <div className="upload-empty-card-heading upload-empty-card-heading--light">
                <span aria-hidden="true" />
                <h3>Before you upload</h3>
              </div>
              <ul className="upload-empty-bullets">
                <li>One row per time period</li>
                <li>Use matching channel activity and spend columns</li>
                <li>Controls are recommended</li>
              </ul>
            </div>

            <div className="content-panel upload-empty-continue-card">
              <span aria-hidden="true" />
              <p>Continue becomes available after a valid CSV is profiled.</p>
            </div>
          </aside>
        )}
      </section>

      {!profile ? (
        <div className="upload-empty-info-strip" role="status">
          <strong>No file uploaded yet.</strong>
          <span>Start by choosing a valid CSV to unlock validation and dataset profiling.</span>
        </div>
      ) : null}

      {profile ? <DatasetProfileLayout profile={profile} groups={columnGroups} onPreview={handleOpenPreview} /> : null}

      {isRemoveConfirmOpen ? (
        <div className="preview-modal-backdrop" role="presentation">
          <section className="remove-file-modal" role="dialog" aria-modal="true" aria-labelledby="remove-file-title">
            <h3 id="remove-file-title">Remove uploaded file?</h3>
            <p>This will clear the current dataset profile and validation results. You can upload another CSV afterward.</p>
            <div className="remove-file-modal-actions">
              <button className="preview-close-button" type="button" onClick={() => setIsRemoveConfirmOpen(false)}>
                Cancel
              </button>
              <button className="remove-file-confirm-button" type="button" onClick={handleRemoveFile}>
                Remove file
              </button>
            </div>
          </section>
        </div>
      ) : null}

      {isPreviewOpen ? (
        <div className="preview-modal-backdrop" role="presentation">
          <section className="preview-modal" role="dialog" aria-modal="true" aria-labelledby="data-preview-title">
            <div className="preview-modal-header">
              <div>
                <h3 id="data-preview-title">Data Preview</h3>
                <p>Showing first 10 rows</p>
              </div>
              <button className="preview-close-button" type="button" onClick={() => setIsPreviewOpen(false)}>
                Close
              </button>
            </div>
            {previewError ? <p className="preview-error">{previewError}</p> : null}
            {!previewError ? (
              <div className="preview-table-shell">
                <table className="preview-table">
                  <thead>
                    <tr>
                      {previewColumns.map((column) => (
                        <th key={column}>{column}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {previewRows.map((row, index) => (
                      <tr key={`${preview?.upload_id ?? "preview"}-${index}`}>
                        {previewColumns.map((column) => (
                          <td key={`${column}-${index}`}>{String(row[column] ?? "")}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </section>
        </div>
      ) : null}
    </WorkflowScaffold>
  );
}
