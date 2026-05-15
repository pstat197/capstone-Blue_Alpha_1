import { useEffect, useMemo, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { createFullGridRun } from "../../../api/runs";
import type { ConfigPreview, WorkflowDraftRequest } from "../../../api/types";
import { createWorkflowDraft, previewWorkflowConfig } from "../../../api/workflows";
import { WorkflowScaffold } from "../components/WorkflowScaffold";
import {
  defaultFullPriorGrid,
  priorGridStorageKey,
  samplerSettings,
  structuralAssumptions,
  structuralSettingsStorageKey,
} from "../data/mockWorkflow";
import {
  type ChannelPriorGrid,
  type ChannelPriorGrids,
  countRunsForGrid,
  detectedChannels,
  getPriorRunLabel,
  makeChannelGrids,
  profileHasBlockingErrors,
  readActiveProfile,
  readKpiColumn,
  readKpiType,
  readRevenueColumn,
  readRevenuePerKpi,
} from "../data/workflowState";

type CheckStatus = "passed" | "warning" | "missing";

type ValidationItem = {
  name: string;
  detail: string;
  status: CheckStatus;
};

function readChannelPriorGrids(channels: string[]): ChannelPriorGrids {
  const fallback = makeChannelGrids(channels);
  const stored = window.localStorage.getItem(priorGridStorageKey);
  if (!stored) {
    return fallback;
  }
  try {
    const parsed = JSON.parse(stored) as ChannelPriorGrids;
    return Object.fromEntries(channels.map((channel) => [channel, { ...fallback[channel], ...(parsed[channel] || {}) }]));
  } catch {
    return fallback;
  }
}

function clampStructuralNumber(value: unknown, min: number, max: number, fallback: number) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.min(max, Math.max(min, parsed));
}

function readStructuralProfile() {
  const stored = window.localStorage.getItem(structuralSettingsStorageKey);
  if (!stored) {
    return structuralAssumptions;
  }

  try {
    const parsed = JSON.parse(stored) as Partial<typeof structuralAssumptions>;
    return {
      alphaM: clampStructuralNumber(parsed.alphaM, 0, 1, structuralAssumptions.alphaM),
      ecM: clampStructuralNumber(parsed.ecM, 0, 3, structuralAssumptions.ecM),
      slopeM: clampStructuralNumber(parsed.slopeM, 0.2, 3, structuralAssumptions.slopeM),
      maxLag: Math.round(clampStructuralNumber(parsed.maxLag, 1, 8, structuralAssumptions.maxLag)),
      adstockDecay: structuralAssumptions.adstockDecay,
    };
  } catch {
    return structuralAssumptions;
  }
}

function statusLabel(status: CheckStatus) {
  if (status === "passed") return "Passed";
  if (status === "warning") return "Warning";
  return "Missing";
}

function formatNumber(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "Unavailable";
  }
  return new Intl.NumberFormat("en-US").format(value);
}

function compactValues(values: Array<number | string>) {
  const unique = Array.from(new Set(values.map(String))).filter(Boolean);
  if (!unique.length) {
    return "Missing";
  }
  if (unique.length <= 5) {
    return unique.join(", ");
  }
  const numeric = unique.map(Number).filter(Number.isFinite);
  if (numeric.length === unique.length) {
    return `${unique.length} values (${Math.min(...numeric)} to ${Math.max(...numeric)})`;
  }
  return `${unique.length} values`;
}

function valuesForEnabledGrids(
  channelPriorGrids: ChannelPriorGrids,
  key: keyof Pick<ChannelPriorGrid, "roi_mu_values" | "roi_sigma_values" | "roi_dist_values">,
): Array<number | string> {
  return Object.values(channelPriorGrids)
    .filter((grid) => grid.enabled)
    .flatMap((grid) => grid[key] as Array<number | string>);
}

export function ReviewRunPage() {
  const navigate = useNavigate();
  const profile = useMemo(() => readActiveProfile(), []);
  const channels = useMemo(() => detectedChannels(profile), [profile]);
  const kpiColumn = readKpiColumn(profile);
  const kpiType = readKpiType(profile);
  const revenueColumn = readRevenueColumn(profile);
  const revenuePerKpi = readRevenuePerKpi();
  const channelPriorGrids = useMemo(() => readChannelPriorGrids(channels), [channels]);
  const structuralProfile = useMemo(() => readStructuralProfile(), []);
  const [preview, setPreview] = useState<ConfigPreview | null>(null);
  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [previewStatus, setPreviewStatus] = useState<"idle" | "loading" | "api" | "error">("idle");
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [isConfirming, setIsConfirming] = useState(false);
  const [isCreatingRun, setIsCreatingRun] = useState(false);
  const [runCreateError, setRunCreateError] = useState<string | null>(null);

  const enabledGrids = Object.values(channelPriorGrids).filter((grid) => grid.enabled);
  const enabledChannelCount = enabledGrids.length;
  const estimatedRuns = enabledGrids.reduce((total, grid) => total + countRunsForGrid(grid), 0);
  const previewRunCount = preview?.estimated_run_count ?? estimatedRuns;
  const timeColumn = profile?.detected.time_candidates[0] ?? "";
  const hasLargeRunWarning = previewRunCount >= 200;
  const runLabel = getPriorRunLabel(channels, channelPriorGrids);
  const missingItems = [
    !profile ? "Complete Step 1: upload and profile a CSV." : "",
    profileHasBlockingErrors(profile) ? "Return to Step 1: resolve upload profile validation errors." : "",
    !timeColumn ? "Return to Step 1: select or provide a time column." : "",
    !kpiColumn ? "Return to Step 2: choose a KPI column." : "",
    kpiType === "revenue" && !revenueColumn ? "Return to Step 2: choose a revenue column." : "",
    kpiType === "non_revenue" && !revenuePerKpi ? "Return to Step 2: enter revenue_per_kpi." : "",
    !channels.length ? "Return to Step 1: upload data with detectable spend channels." : "",
    enabledChannelCount === 0 ? "Return to Step 3: select at least one channel." : "",
    estimatedRuns <= 0 && enabledChannelCount > 0 ? "Return to Step 3: configure at least one prior-grid value." : "",
  ].filter(Boolean);
  const isComplete = missingItems.length === 0 && Boolean(profile);

  const workflowRequest = useMemo<WorkflowDraftRequest | null>(() => {
    if (!profile || !isComplete) {
      return null;
    }
    return {
      upload_id: profile.upload_id,
      name: `${profile.filename} prior-sensitivity analysis`,
      dataset: {
        data_csv: profile.storage_path,
        filename: profile.filename,
        channels,
      },
      column_mapping: {
        time_col: timeColumn,
        kpi_col: kpiColumn,
        geo_col: profile.detected.geo_candidates[0] ?? null,
        population_col: profile.detected.population_candidates[0] ?? null,
        channels,
      },
      outcome: {
        kpi_col: kpiColumn,
        kpi_type: kpiType,
        revenue_col: kpiType === "revenue" ? revenueColumn : null,
        revenue_per_kpi: kpiType === "non_revenue" ? revenuePerKpi : null,
      },
      prior_grid: {
        roi_mu_values: defaultFullPriorGrid.muValues,
        roi_sigma_values: defaultFullPriorGrid.sigmaValues,
        roi_dist_values: defaultFullPriorGrid.distributions,
        channel_prior_grids: channelPriorGrids,
      },
      structural: {
        alpha_m_values: [structuralProfile.alphaM],
        ec_m_values: [structuralProfile.ecM],
        slope_m_values: [structuralProfile.slopeM],
        max_lag_values: [structuralProfile.maxLag],
        adstock_decay_values: [structuralProfile.adstockDecay],
      },
      sampler: {
        n_chains: samplerSettings.nChains,
        n_adapt: samplerSettings.nAdapt,
        n_burnin: samplerSettings.nBurnin,
        n_keep: samplerSettings.nKeep,
        seed: samplerSettings.seed,
        parallel_workers: samplerSettings.parallelWorkers,
      },
    };
  }, [channelPriorGrids, channels, isComplete, kpiColumn, kpiType, profile, revenueColumn, revenuePerKpi, structuralProfile, timeColumn]);

  useEffect(() => {
    if (!workflowRequest) {
      setPreview(null);
      setWorkflowId(null);
      setPreviewStatus("idle");
      return;
    }

    let cancelled = false;
    setPreviewStatus("loading");
    setPreviewError(null);
    createWorkflowDraft(workflowRequest)
      .then((draft) => {
        if (cancelled) {
          throw new Error("Config preview request cancelled.");
        }
        setWorkflowId(draft.workflow_id);
        return previewWorkflowConfig(draft.workflow_id);
      })
      .then((apiPreview) => {
        if (cancelled) {
          return;
        }
        setPreview(apiPreview);
        setPreviewStatus("api");
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        setPreview(null);
        setWorkflowId(null);
        setPreviewStatus("error");
        setPreviewError(error instanceof Error ? error.message : "Unable to generate backend config.");
      });

    return () => {
      cancelled = true;
    };
  }, [workflowRequest]);

  const canCreateRun = Boolean(isComplete && workflowId && preview && !preview.errors.length && !isCreatingRun);
  const backendReadyStatus: CheckStatus = !isComplete || previewStatus === "error" || (preview && preview.errors.length) ? "missing" : previewStatus === "api" ? "passed" : "warning";
  const validationItems: ValidationItem[] = [
    {
      name: "Dataset uploaded and profiled",
      detail: profile ? `${profile.filename} (${formatNumber(profile.row_count)} rows, ${formatNumber(profile.columns.length)} columns)` : "Complete Step 1 before running.",
      status: profile && !profileHasBlockingErrors(profile) ? "passed" : "missing",
    },
    { name: "Time column selected", detail: timeColumn || "Missing in Step 1.", status: timeColumn ? "passed" : "missing" },
    {
      name: "KPI, KPI type, and revenue settings complete",
      detail: kpiColumn
        ? kpiType === "non_revenue"
          ? `${kpiColumn}; non-revenue; revenue_per_kpi=${revenuePerKpi ?? "missing"}`
          : `${kpiColumn}; revenue KPI; revenue column=${revenueColumn || "missing"}`
        : "Missing in Step 2.",
      status: kpiColumn && ((kpiType === "non_revenue" && revenuePerKpi) || (kpiType === "revenue" && revenueColumn)) ? "passed" : "missing",
    },
    {
      name: "Channels detected and selected",
      detail: enabledChannelCount ? `${enabledChannelCount} of ${channels.length} detected channels selected.` : "Select channels in Step 3.",
      status: enabledChannelCount ? "passed" : "missing",
    },
    {
      name: "Prior grid configured",
      detail: estimatedRuns > 0 ? `${formatNumber(estimatedRuns)} model fits from the current prior grid.` : "Configure prior grid in Step 3.",
      status: estimatedRuns > 0 ? "passed" : "missing",
    },
    {
      name: "Structural settings configured",
      detail: `alpha ${structuralProfile.alphaM}, ec ${structuralProfile.ecM}, slope ${structuralProfile.slopeM}, lag ${structuralProfile.maxLag}.`,
      status: "passed",
    },
    {
      name: "Sampler/backend settings configured",
      detail: `${samplerSettings.nChains} chains, ${samplerSettings.parallelWorkers} workers, keep ${samplerSettings.nKeep}, seed ${samplerSettings.seed}.`,
      status: "passed",
    },
    {
      name: "Estimated run count generated",
      detail: estimatedRuns > 0 ? `${formatNumber(previewRunCount)} model fits can be computed.` : "Run count unavailable.",
      status: estimatedRuns > 0 ? (hasLargeRunWarning ? "warning" : "passed") : "missing",
    },
    {
      name: "Backend config generated successfully",
      detail: previewStatus === "loading"
        ? "Generating backend config from current settings."
        : preview?.errors.length
          ? preview.errors.join(" ")
          : previewStatus === "api"
            ? "Config compiled with no blocking errors."
            : previewError || "Waiting for a complete frontend state.",
      status: backendReadyStatus,
    },
  ];
  const blockingItems = validationItems.filter((item) => item.status === "missing");
  const warningMessages = [
    hasLargeRunWarning ? "Run count is determined by your selected prior-grid configuration. Large grids may take longer to complete." : "",
    ...(preview?.warnings || []).filter((message) => !/preview only|phase 3|sensitivity\.yaml/i.test(message)),
  ].filter(Boolean);

  const runSummaryRows = [
    ["Run type", `${runLabel.label} (${formatNumber(previewRunCount)} model fits)`],
    ["Prior grid mode", runLabel.priorGridMode],
    ["Selected channels", `${enabledChannelCount} selected`],
    ["MU values summary", compactValues(valuesForEnabledGrids(channelPriorGrids, "roi_mu_values"))],
    ["Sigma values summary", compactValues(valuesForEnabledGrids(channelPriorGrids, "roi_sigma_values"))],
    ["Distribution summary", compactValues(valuesForEnabledGrids(channelPriorGrids, "roi_dist_values"))],
    ["Estimated model fits", formatNumber(previewRunCount)],
    ["Backend target", "Meridian pipeline / CmdStanPy"],
    ["Output artifacts", "Run tables, report inputs, diagnostics, HTML dashboard"],
    ["Results location", "Runs page, then Results pages for completed artifacts"],
  ];

  const handleConfirmRun = () => {
    if (!workflowId || !preview) {
      return;
    }
    setIsCreatingRun(true);
    setRunCreateError(null);
    createFullGridRun({ workflow_id: workflowId, approved_config_preview: preview, mode: "real_full" })
      .then((run) => navigate(run.monitor_url || `/runs/${run.run_id}/monitor`))
      .catch((error: unknown) => setRunCreateError(error instanceof Error ? error.message : "Unable to start this configuration."))
      .finally(() => {
        setIsCreatingRun(false);
        setIsConfirming(false);
      });
  };

  return (
    <WorkflowScaffold
      title="Review, Validate & Run"
      summary="Final check before sending this configuration to the backend. The run will execute exactly the prior grid you designed."
      hidePrimaryAction
    >
      <section className="review-summary-bar" aria-label="Run configuration summary">
        <div><span>Dataset</span><strong>{profile?.filename ?? "Not selected"}</strong><small>{profile ? `${formatNumber(profile.row_count)} rows` : "Upload required"}</small></div>
        <div><span>KPI</span><strong>{kpiColumn || "Missing"}</strong><small>{kpiType === "non_revenue" ? "non-revenue KPI" : "revenue KPI"}</small></div>
        <div><span>{kpiType === "non_revenue" ? "Revenue per KPI" : "Revenue column"}</span><strong>{kpiType === "non_revenue" ? revenuePerKpi ?? "Missing" : revenueColumn || "Missing"}</strong><small>{kpiType === "non_revenue" ? "revenue-equivalent ROI" : "direct revenue"}</small></div>
        <div><span>Channels</span><strong>{enabledChannelCount ? `${enabledChannelCount} selected` : "Missing"}</strong><small>{channels.length ? `${channels.length} detected` : "No channels detected"}</small></div>
        <div><span>Estimated model fits</span><strong>{isComplete ? formatNumber(previewRunCount) : "Unavailable"}</strong><small>Determined by your grid</small></div>
        <div><span>Run mode</span><strong>{runLabel.label}</strong><small>{runLabel.description}</small></div>
      </section>

      {warningMessages.length ? (
        <section className="review-warning-strip">
          {warningMessages.map((message) => <p key={message}>{message}</p>)}
        </section>
      ) : null}

      {!profile ? (
        <section className="review-empty-state">
          <div>
            <h3>Complete the previous steps before running.</h3>
            <p>Once a dataset and configuration exist, this page will validate the current frontend state and prepare the backend config internally.</p>
          </div>
          <NavLink className="secondary-nav-button" to="/workflow/upload">Edit previous steps</NavLink>
        </section>
      ) : null}

      <section className="review-run-layout">
        <div className="content-panel review-validation-panel">
          <div className="section-title-row">
            <div>
              <span className="eyebrow">Validation status</span>
              <h3>{blockingItems.length ? "Needs attention before launch" : "Configuration ready"}</h3>
              <p>Checks are generated from the current uploaded dataset and selected workflow settings.</p>
            </div>
          </div>
          <div className="review-checklist">
            {validationItems.map((item) => (
              <div className={`review-check-row review-check-row--${item.status}`} key={item.name}>
                <span className="review-check-icon" aria-hidden="true">{item.status === "passed" ? "OK" : item.status === "warning" ? "!" : "X"}</span>
                <div>
                  <strong>{item.name}</strong>
                  <small>{item.detail}</small>
                </div>
                <span className={`review-status-badge review-status-badge--${item.status}`}>{statusLabel(item.status)}</span>
              </div>
            ))}
          </div>
          <div className={`review-readiness-note ${blockingItems.length ? "review-readiness-note--missing" : "review-readiness-note--passed"}`}>
            <strong>{blockingItems.length ? "Previous steps need attention." : "All blocking checks passed."}</strong>
            <span>{blockingItems.length ? missingItems[0] : "The backend config is ready to send when you confirm the run."}</span>
          </div>
        </div>

        <div className="review-launch-column">
          <div className="content-panel">
            <div className="section-title-row">
              <div>
                <span className="eyebrow">Run summary</span>
                <h3>What will be sent</h3>
              </div>
            </div>
            <div className="review-summary-table">
              {runSummaryRows.map(([label, value]) => (
                <div key={label}>
                  <strong>{label}</strong>
                  <span>{value}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="content-panel review-launch-card">
            <h3>{blockingItems.length ? "Configuration incomplete" : "Ready to run this configuration?"}</h3>
            <p>{blockingItems.length ? "Complete the missing checklist items before launching." : "Executes the configured prior-sensitivity grid using the current settings."}</p>
            <button className="primary-action primary-action--enabled review-run-button" disabled={!canCreateRun} type="button" onClick={() => setIsConfirming(true)}>
              {isCreatingRun ? "Starting Run..." : "Run This Configuration"}
            </button>
            <small>After the run starts, progress and results will appear on the Runs page.</small>
            {runCreateError ? <p className="review-error-text">Run start failed: {runCreateError}</p> : null}
          </div>
        </div>
      </section>

      <section className="review-next-strip" aria-label="What happens next">
        <div><strong>Backend receives this exact configuration</strong><span>The current frontend state is compiled internally before launch.</span></div>
        <div><strong>Model fits follow the selected grid</strong><span>No valid large grid is reduced by this page.</span></div>
        <div><strong>Results are saved to this workspace</strong><span>Run tables, reports, and dashboard artifacts are written under output folders.</span></div>
        <div><strong>Monitor from the Runs page</strong><span>Progress is shown first; completed artifacts feed the Results pages.</span></div>
      </section>

      {isConfirming ? (
        <div className="review-modal-backdrop" role="presentation">
          <div className="review-modal" role="dialog" aria-modal="true" aria-labelledby="confirm-run-title">
            <h3 id="confirm-run-title">Confirm Run</h3>
            <div className="review-summary-table review-summary-table--modal">
              {[
                ["Dataset", profile?.filename ?? "Not selected"],
                ["KPI", kpiColumn || "Missing"],
                ["Selected channels", `${enabledChannelCount} selected`],
                ["Estimated model fits", formatNumber(previewRunCount)],
                ["Run mode", runLabel.label],
                ["Backend target", "Meridian pipeline / CmdStanPy"],
                ["Output location", "Saved to this workspace and visible from Runs"],
              ].map(([label, value]) => (
                <div key={label}>
                  <strong>{label}</strong>
                  <span>{value}</span>
                </div>
              ))}
            </div>
            <div className="review-modal-actions">
              <button className="secondary-link" disabled={isCreatingRun} type="button" onClick={() => setIsConfirming(false)}>Cancel</button>
              <button className="primary-action primary-action--enabled" disabled={!canCreateRun} type="button" onClick={handleConfirmRun}>
                {isCreatingRun ? "Starting..." : "Confirm & Run"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </WorkflowScaffold>
  );
}
