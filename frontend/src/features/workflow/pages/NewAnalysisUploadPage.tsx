import type { ChangeEvent, DragEvent } from "react";
import { useMemo, useRef, useState } from "react";
import { createUpload, getUploadPreview, getUploadProfile, loadMonthlyMochaExample } from "../../../api/uploads";
import type { CsvPreview, CsvProfile } from "../../../api/types";
import { StatusBadge } from "../components/StatusBadge";
import { WorkflowScaffold } from "../components/WorkflowScaffold";
import { revenuePerKpiStorageKey } from "../data/mockWorkflow";
import {
  clearActiveProfile,
  clearDatasetSelections,
  detectedChannels,
  readActiveProfile,
  readRevenuePerKpi,
  writeActiveProfile,
} from "../data/workflowState";

type ColumnRow = { name: string; role: string; status: "valid" | "warning" | "missing"; detail?: string };
type ColumnGroups = {
  time: ColumnRow[];
  kpi: ColumnRow[];
  media: ColumnRow[];
  optional: ColumnRow[];
};

function ColumnGroup({
  title,
  eyebrow,
  rows,
  variant,
}: {
  title: string;
  eyebrow?: string;
  rows: ColumnRow[];
  variant?: "default" | "chips" | "optional";
}) {
  return (
    <section className={`column-group column-group--${variant ?? "default"}`}>
      <div className="column-group-heading">
        <h3>{title}</h3>
        {eyebrow ? <span>{eyebrow}</span> : null}
      </div>
      <div className="column-list">
        {rows.map((row) => (
          <div className={`column-row column-row--${row.status}`} key={`${title}-${row.name}`}>
            <div>
              <strong>{row.name}</strong>
              <span>{row.role}</span>
              {row.detail ? <small>{row.detail}</small> : null}
            </div>
            <StatusBadge status={row.status} />
          </div>
        ))}
      </div>
    </section>
  );
}

function columnDetail(profile: CsvProfile, name: string): string {
  const column = profile.columns.find((item) => item.name === name);
  if (!column) {
    return "";
  }
  return `${column.inferred_type}, ${Math.round(column.null_rate * 100)}% null`;
}

function profileToColumnGroups(profile: CsvProfile): ColumnGroups {
  return {
    time: profile.detected.time_candidates.map((name) => ({
      name,
      role: "Date/time candidate",
      status: "valid",
      detail: columnDetail(profile, name),
    })),
    kpi: profile.detected.kpi_candidates.map((name) => ({
      name,
      role: "KPI candidate",
      status: "valid",
      detail: columnDetail(profile, name),
    })),
    media: profile.detected.spend_channel_candidates.map((item) => ({
      name: item.column,
      role: `${item.channel.toUpperCase()} spend`,
      status: "valid",
      detail: columnDetail(profile, item.column),
    })),
    optional: [
      ...profile.detected.media_activity_candidates.map((item) => ({
        name: item.column,
        role: `${item.channel.toUpperCase()} media activity`,
        status: "valid" as const,
        detail: columnDetail(profile, item.column),
      })),
      ...profile.detected.revenue_candidates.map((name) => ({
        name,
        role: "Revenue candidate",
        status: "valid" as const,
        detail: columnDetail(profile, name),
      })),
      ...(profile.detected.revenue_candidates.length ? [] : [{ name: "revenue", role: "Revenue column", status: "missing" as const, detail: "Not detected; revenue_per_kpi may be required." }]),
      ...profile.detected.control_candidates.map((name) => ({
        name,
        role: "Control candidate",
        status: "valid" as const,
        detail: columnDetail(profile, name),
      })),
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

function validationDetail(label: string) {
  const lower = label.toLowerCase();
  if (lower.includes("date") || lower.includes("time")) {
    return "Required for time-series indexing";
  }
  if (lower.includes("kpi")) {
    return "Choose one on the next step";
  }
  if (lower.includes("active channel") || lower.includes("spend")) {
    return "Used to detect channel priors";
  }
  if (lower.includes("activity")) {
    return "Recommended for Meridian media inputs";
  }
  if (lower.includes("revenue")) {
    return "Use a revenue column or revenue_per_kpi";
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

const exampleColumns = [
  "date",
  "subscriptions",
  "revenue_per_subscription",
  "meta_impressions",
  "meta_spend",
  "google_clicks",
  "google_spend",
  "tiktok_impressions",
  "tiktok_spend",
  "promo",
  "competitor_sales",
];

const exampleRows = [
  ["2024-01-01", "1245", "42.50", "1234567", "12345.67", "45678", "8765.43", "789012", "6543.21", "0.12", "98765"],
  ["2024-01-08", "1312", "41.80", "1345678", "13210.11", "47890", "9012.34", "812345", "6987.65", "0.10", "101234"],
  ["2024-01-15", "1398", "43.10", "1456789", "13987.65", "49123", "9543.21", "845678", "7234.56", "0.15", "103456"],
];

const exampleCsvHref = `data:text/csv;charset=utf-8,${encodeURIComponent(
  [exampleColumns.join(","), ...exampleRows.map((row) => row.join(","))].join("\n"),
)}`;

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
  const [revenuePerKpi, setRevenuePerKpi] = useState<number | null>(readRevenuePerKpi);
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
      optional: [],
    };
  }, [profile]);

  const validationBadges = (profile?.validation_badges ?? []).filter((badge) => !isGeoPopulationLabel(badge.label));

  const hasRevenueColumn = profile ? profile.detected.revenue_candidates.length > 0 : false;

  const profileSummary = {
    filename: profile?.filename ?? "",
    rows: profile?.row_count ?? 0,
    channels:
      detectedChannels(profile ?? null).length,
    kpi: profile?.detected.kpi_candidates[0] ?? "Not detected",
    dateRange: profile ? "Detected from upload" : "",
  };

  const revenueAssumptionIsValid = hasRevenueColumn || (revenuePerKpi !== null && Number.isFinite(revenuePerKpi) && revenuePerKpi > 0);
  const canContinue = hasRequiredUploadFields(profile) && revenueAssumptionIsValid;
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
        setRevenuePerKpi(null);
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

  const handleLoadExampleDataset = () => {
    setUploadStatus("uploading");
    setUploadError(null);
    setReplacementWarning(null);
    loadMonthlyMochaExample()
      .then((upload) => getUploadProfile(upload.upload_id))
      .then((apiProfile) => {
        clearDatasetSelections();
        writeActiveProfile(apiProfile);
        setProfile(apiProfile);
        setRevenuePerKpi(null);
        setUploadStatus("api");
        setPreview(null);
        setPreviewError(null);
      })
      .catch((error: unknown) => {
        setUploadStatus(profile ? "api" : "error");
        setUploadError(error instanceof Error ? error.message : "Unable to load the example dataset.");
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

  const handleRevenuePerKpiChange = (event: ChangeEvent<HTMLInputElement>) => {
    const nextValue = Number(event.currentTarget.value);
    setRevenuePerKpi(nextValue);
    if (Number.isFinite(nextValue) && nextValue > 0) {
      window.localStorage.setItem(revenuePerKpiStorageKey, String(nextValue));
    }
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
    window.localStorage.removeItem(revenuePerKpiStorageKey);
    setRevenuePerKpi(null);
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
      <section className="upload-onboarding-grid">
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
                  <a className="download-example-link" href={exampleCsvHref} download="meridian_example.csv">
                    Download example CSV
                  </a>
                  <button className="download-example-link" type="button" onClick={handleLoadExampleDataset}>
                    Load example dataset
                  </button>
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
              <div className="dataset-file-icon" aria-hidden="true">CSV</div>
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
              <input ref={replaceInputRef} id="replace-csv-input" className="visually-hidden" type="file" accept=".csv,text/csv" onChange={handleFileChange} />
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
            <div className="validation-list">
              {validationBadges.map((badge) => (
                <div className="validation-item" key={badge.label}>
                  <StatusBadge status={validationStatusClass(badge.status)} />
                  <div>
                    <strong>{compactValidationLabel(badge.label)}</strong>
                    <span>{validationDetail(badge.label)}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {!hasRevenueColumn ? (
            <div className="content-panel revenue-required-card">
              <div>
                <h3>Revenue assumption required</h3>
                <p>
                  No revenue column was detected. Because the KPI is non-revenue, enter the value of one KPI unit so the model can report revenue-equivalent ROI.
                </p>
              </div>
              <label className="revenue-input-field">
                <span>Revenue per KPI</span>
                <div className="revenue-input-shell">
                  <input
                    type="number"
                    min="0"
                    step="0.1"
                    value={revenuePerKpi !== null && Number.isFinite(revenuePerKpi) ? revenuePerKpi : ""}
                    onChange={handleRevenuePerKpiChange}
                    aria-label="Revenue per KPI"
                  />
                  <span>USD per KPI</span>
                </div>
              </label>
              <p className="revenue-helper-text">Use your business-defined value for one selected KPI unit.</p>
            </div>
          ) : null}
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

      {profile ? <section className="content-panel dataset-profile-panel">
        <div className="section-title-row">
          <div>
            <h3>Dataset Profile</h3>
            <p>We have profiled your file and mapped the key fields below.</p>
          </div>
          <button className="preview-data-button" type="button" onClick={handleOpenPreview}>
            Preview data
          </button>
        </div>
        <div className="column-profile-grid">
          <ColumnGroup title="Time" rows={columnGroups.time} />
          <ColumnGroup title="KPI" rows={columnGroups.kpi} />
          <ColumnGroup title="Paid media spend columns" eyebrow={`${columnGroups.media.length} channels`} rows={columnGroups.media} variant="chips" />
          <ColumnGroup title="Optional / missing fields" rows={columnGroups.optional} variant="optional" />
        </div>
      </section> : null}

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
