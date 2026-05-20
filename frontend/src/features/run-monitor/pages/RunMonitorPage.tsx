import { useEffect, useMemo, useState } from "react";
import { Link, NavLink, useParams, useSearchParams } from "react-router-dom";
import { advanceMockRun, getRunLogs, getRunStatus } from "../../../api/runs";
import { getWorkflowDraft } from "../../../api/workflows";
import type { RunLifecycleStatus, RunStatus, WorkflowDraft } from "../../../api/types";
import { writeActiveResultsRunId } from "../../results/data/resultLoader";
import { formatNumber } from "../../results/data/resultSelectors";
import { ChannelLogo, displayChannelName } from "../../workflow/data/channelRegistry";
import { activeRunIdStorageKey } from "../../workflow/data/workflowState";

type StageState = "complete" | "active" | "pending" | "failed";

const workflowSteps = [
  ["Upload Data", "/workflow/upload"],
  ["KPI & Revenue Setup", "/workflow/kpi-revenue"],
  ["Prior Grid Setup", "/workflow/prior-grid"],
  ["Structural Settings", "/workflow/structural-settings"],
  ["Review & Start Run", "/workflow/review-run"],
];

function labelForStatus(status?: string) {
  if (status === "already_completed") return "Completed";
  if (status === "completed") return "Completed";
  if (status === "failed") return "Failed";
  if (status === "cancelled") return "Cancelled";
  if (status === "running") return "Running";
  return "Queued";
}

function summaryStatusLabel(status?: string) {
  if (status === "already_completed") return "EXISTING RESULT";
  if (status === "completed") return "COMPLETED";
  if (status === "failed" || status === "cancelled") return "FAILED";
  if (status === "queued") return "QUEUED";
  return "RUN IN PROGRESS";
}

function formatTime(raw?: string | null) {
  if (!raw) return "Pending";
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return "Pending";
  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  }).format(parsed);
}

function formatStarted(raw?: string | null) {
  if (!raw) return "Not started";
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return "Not started";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(parsed);
}

function formatDuration(seconds: number) {
  if (seconds <= 0) return "Calculating...";
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  if (minutes <= 0) return `${remainder}s`;
  return `${minutes}m ${remainder.toString().padStart(2, "0")}s`;
}

function elapsedSeconds(run: RunStatus | null) {
  if (!run?.started_at) return 0;
  const end = run.completed_at ? new Date(run.completed_at).getTime() : Date.now();
  return Math.max(0, Math.round((end - new Date(run.started_at).getTime()) / 1000));
}

function estimatedRemainingLabel(run: RunStatus | null) {
  if (!run) return "Calculating...";
  if (run.status === "already_completed") return "Complete";
  if (run.status === "completed") return "Complete";
  if (run.status === "failed" || run.status === "cancelled") return "Unavailable";
  const completed = run.progress.completed_runs + run.progress.failed_runs;
  const total = run.progress.total_runs;
  const elapsed = elapsedSeconds(run);
  if (!run.started_at || completed <= 0 || total <= 0 || completed >= total || elapsed <= 0) {
    return "Calculating...";
  }
  const secondsPerRun = elapsed / completed;
  return formatDuration(Math.round((total - completed) * secondsPerRun));
}

function progressPercent(run: RunStatus | null) {
  const total = run?.progress.total_runs ?? 0;
  if (!total) return 0;
  return Math.min(100, Math.round(((run?.progress.completed_runs ?? 0) / total) * 100));
}

function channelPercent(completed: number, total: number) {
  if (!total) return 0;
  return Math.min(100, Math.round((completed / total) * 100));
}

function pillTone(status: RunLifecycleStatus | string) {
  if (status === "completed" || status === "already_completed") return "complete";
  if (status === "running") return "running";
  if (status === "failed" || status === "cancelled") return "failed";
  return "pending";
}

function isFinalizing(run: RunStatus | null) {
  if (!run || run.status !== "running") return false;
  const accountedFor = run.progress.completed_runs + run.progress.failed_runs;
  return run.progress.total_runs > 0 && accountedFor >= run.progress.total_runs;
}

function activeStageIndex(run: RunStatus | null) {
  if (!run || run.status === "queued") return 0;
  if (run.status === "completed" || run.status === "already_completed") return 4;
  if (run.status === "failed" || run.status === "cancelled") {
    if (!run.started_at) return 0;
    return isFinalizing(run) ? 3 : 2;
  }
  if (isFinalizing(run)) return 3;
  if ((run.progress.completed_runs + run.progress.failed_runs) > 0 || run.progress.active_target_channel) return 2;
  return 1;
}

function timelineState(run: RunStatus | null, index: number): StageState {
  const active = activeStageIndex(run);
  if ((run?.status === "failed" || run?.status === "cancelled") && index === active) return "failed";
  if (run?.status === "completed" || run?.status === "already_completed" || index < active) return "complete";
  if (index === active) return "active";
  return "pending";
}

function workflowValue(workflow: WorkflowDraft | null, section: string, key: string) {
  const source = workflow?.[section as keyof WorkflowDraft];
  if (!source || typeof source !== "object") return null;
  const value = (source as Record<string, unknown>)[key];
  return value === undefined || value === null || value === "" ? null : value;
}

function revenueHandling(workflow: WorkflowDraft | null) {
  const revenueColumn = workflowValue(workflow, "outcome", "revenue_col");
  const revenuePerKpi = workflowValue(workflow, "outcome", "revenue_per_kpi");
  if (revenueColumn) return "direct revenue column";
  if (revenuePerKpi) return `revenue_per_kpi = ${revenuePerKpi}`;
  return "Unavailable";
}

function dateRange(workflow: WorkflowDraft | null) {
  const dataset = workflow?.dataset ?? {};
  const start = dataset.date_min ?? dataset.start_date;
  const end = dataset.date_max ?? dataset.end_date;
  if (start && end) return `${start} -> ${end}`;
  return "Unavailable";
}

export function RunMonitorPage() {
  const params = useParams();
  const [searchParams] = useSearchParams();
  const queryRunId = searchParams.get("run_id")?.trim() || null;
  const reusedExistingResult = searchParams.get("reused") === "1";
  const routeRunId = params.runId && params.runId !== "current" ? params.runId : null;
  const sessionRunId = window.sessionStorage.getItem(activeRunIdStorageKey)?.trim() || null;
  const demoRunsEnabled = import.meta.env.DEV && import.meta.env.VITE_ENABLE_DEMO_RUNS === "true";
  const explicitDemoRunId = demoRunsEnabled && searchParams.get("demo") === "true" ? "demo_32run" : null;
  const resolvedRunId = queryRunId || routeRunId || sessionRunId || explicitDemoRunId;
  const [run, setRun] = useState<RunStatus | null>(null);
  const [workflow, setWorkflow] = useState<WorkflowDraft | null>(null);
  const [logLines, setLogLines] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isAdvancing, setIsAdvancing] = useState(false);
  const [showFullLogs, setShowFullLogs] = useState(false);

  const loadRun = () => {
    if (!resolvedRunId) {
      setRun(null);
      setWorkflow(null);
      setLogLines([]);
      setError(null);
      return;
    }
    getRunStatus(resolvedRunId)
      .then((status) => {
        setRun(status);
        setError(null);
        getWorkflowDraft(status.workflow_id).then(setWorkflow).catch(() => setWorkflow(null));
        return getRunLogs(resolvedRunId);
      })
      .then((logs) => {
        setLogLines(logs.lines);
      })
      .catch((loadError: unknown) => {
        setRun(null);
        setError(loadError instanceof Error ? loadError.message : "Run status unavailable.");
      });
  };

  useEffect(() => {
    if (!resolvedRunId) {
      setRun(null);
      setWorkflow(null);
      setLogLines([]);
      setError(null);
      return;
    }
    loadRun();
  }, [resolvedRunId]);

  useEffect(() => {
    if (!resolvedRunId || !run || (run.status !== "queued" && run.status !== "running")) {
      return undefined;
    }
    const timer = window.setInterval(loadRun, 2500);
    return () => window.clearInterval(timer);
  }, [run?.status, resolvedRunId]);

  useEffect(() => {
    if ((run?.status === "completed" || run?.status === "already_completed") && run.run_id) {
      writeActiveResultsRunId(run.run_id);
    }
  }, [run?.run_id, run?.status]);

  const percentComplete = useMemo(() => progressPercent(run), [run]);
  const activeChannel = run?.progress.active_target_channel;
  const hasResults = Boolean(
    (run?.status === "completed" || run?.status === "already_completed") &&
    (run.result_url || run.result_artifacts?.dashboard_payload)
  );
  const resultsUrl =
    (run?.status === "completed" || run?.status === "already_completed") && run?.run_id
      ? run.result_url && (run.result_url.includes("run_id=") || run.result_url.includes("history_id=") || run.result_url.includes(`/results/${run.run_id}/`))
        ? run.result_url
        : `/results/overview?run_id=${encodeURIComponent(run.run_id)}`
      : null;
  const isFailed = run?.status === "failed" || run?.status === "cancelled";
  const isDevelopmentMock = import.meta.env.DEV && run?.mode === "mock";
  const runSource = run?.mode === "real_full" || run?.mode === "real_tiny" ? "FastAPI" : isDevelopmentMock ? "Mock execution" : "FastAPI";
  const completedCombinations = run?.progress.completed_runs ?? 0;
  const failedCombinations = run?.progress.failed_runs ?? 0;
  const totalCombinations = run?.progress.total_runs ?? 0;
  const runStatus = isFinalizing(run) ? "Finalizing" : labelForStatus(run?.status);
  const pageSubtitle = !resolvedRunId
    ? "Start a run from Review & Start Run, or open a completed run from Results History."
    : isFailed
    ? "The run failed before completion. Review the error details below."
    : run?.status === "already_completed" || reusedExistingResult
      ? "Existing completed result found. This saved result is ready to review."
    : run?.status === "completed"
      ? "Your run has completed. Results are ready to review."
      : "Your run is in progress. Keep this page open to monitor execution status.";

  const timeline = [
    {
      title: "Queued",
      time: formatTime(run?.created_at),
      description: "Run request accepted by the backend",
    },
    {
      title: "Initializing",
      time: run?.started_at ? formatTime(run.started_at) : "Pending",
      description: "Loading configuration and preparing jobs",
    },
    {
      title: "Running Meridian",
      time: activeStageIndex(run) >= 2 ? (activeChannel ? displayChannelName(activeChannel) : "In progress") : "Pending",
      description: "Executing target-channel combinations",
    },
    {
      title: "Finalizing",
      time: activeStageIndex(run) >= 3 ? "In progress" : "Pending",
      description: "Aggregating outputs and calculating metrics",
    },
    {
      title: "Completed",
      time: run?.completed_at ? formatTime(run.completed_at) : "Pending",
      description: "Results ready",
    },
  ];

  const detailRows = [
    ["Configuration ID", run?.workflow_id ?? "Unavailable"],
    ["Result ID", run?.display_result_id ?? run?.output_tag ?? run?.run_id ?? "Unavailable"],
    ["Config ID", run?.config_fingerprint ?? "Unavailable"],
    ["KPI", String(workflowValue(workflow, "outcome", "kpi_col") ?? "Unavailable")],
    ["Revenue handling", revenueHandling(workflow)],
    ["Total combinations", totalCombinations ? `${formatNumber(totalCombinations)} (${formatNumber(run?.channel_progress.length ?? 0)} channels)` : "Unavailable"],
    ["Date range", dateRange(workflow)],
    ["Timezone", String(workflowValue(workflow, "dataset", "timezone") ?? Intl.DateTimeFormat().resolvedOptions().timeZone ?? "Unavailable")],
    ["Run source", runSource],
  ];

  const activityLines = [
    ...(run?.messages ?? []),
    ...logLines.slice(-4),
  ].slice(-8);

  const handleAdvance = () => {
    if (!resolvedRunId) {
      return;
    }
    setIsAdvancing(true);
    advanceMockRun(resolvedRunId)
      .then((status) => {
        setRun(status);
        setError(null);
      })
      .catch((advanceError: unknown) => {
        setError(advanceError instanceof Error ? advanceError.message : "Unable to advance mock run.");
      })
      .finally(() => {
        setIsAdvancing(false);
      });
  };

  if (!resolvedRunId) {
    return (
      <article className="workflow-page run-monitor-page">
        <div className="page-heading">
          <div className="page-heading-copy">
            <span className="eyebrow">Execution</span>
            <h2>Run Monitor</h2>
            <p className="page-summary">{pageSubtitle}</p>
          </div>
          <nav className="wizard-steps run-monitor-stepper" aria-label="Workflow steps">
            {workflowSteps.map(([label, path], index) => (
              <NavLink className={`wizard-step ${index < 4 ? "wizard-step--complete" : "wizard-step--active"}`} key={label} to={path}>
                <span>{index + 1}</span>
                <strong>{label}</strong>
              </NavLink>
            ))}
          </nav>
        </div>

        <section className="content-panel run-monitor-empty-state">
          <div>
            <h3>No active run selected</h3>
            <p>Start a run from Review & Start Run, or open a completed run from Results History.</p>
          </div>
          <Link className="secondary-link" to="/workflow/review-run">Back to Review</Link>
        </section>
      </article>
    );
  }

  return (
    <article className="workflow-page run-monitor-page">
      <div className="page-heading">
        <div className="page-heading-copy">
          <span className="eyebrow">Execution</span>
          <h2>Run Monitor</h2>
          <p className="page-summary">{pageSubtitle}</p>
        </div>
        <nav className="wizard-steps run-monitor-stepper" aria-label="Workflow steps">
          {workflowSteps.map(([label, path], index) => (
            <NavLink className={`wizard-step ${index < 4 ? "wizard-step--complete" : "wizard-step--active"}`} key={label} to={path}>
              <span>{index + 1}</span>
              <strong>{label}</strong>
            </NavLink>
          ))}
        </nav>
      </div>

      {error ? (
        <section className="content-panel run-monitor-error">
          <h3>Status unavailable</h3>
          <p>{error}</p>
        </section>
      ) : null}

      <section className={`run-summary-card run-summary-card--${pillTone(run?.status ?? "queued")}`}>
        <div className="run-summary-identity">
          <span className={`run-status-orb run-status-orb--${pillTone(run?.status ?? "queued")}`} aria-hidden="true" />
          <div>
            <span className="run-summary-state">{summaryStatusLabel(run?.status)}</span>
            <strong>{run?.display_result_id || run?.output_tag || run?.run_id || resolvedRunId}</strong>
            <small>{run?.status === "already_completed" || reusedExistingResult ? "Saved result reused" : `Started ${formatStarted(run?.started_at)}`}</small>
          </div>
        </div>
        <div className="run-summary-metrics">
          <div>
            <span>Estimated time remaining</span>
            <strong>{estimatedRemainingLabel(run)}</strong>
            <small>{elapsedSeconds(run) ? `${formatDuration(elapsedSeconds(run))} elapsed` : "Waiting for backend progress"}</small>
          </div>
          <div>
            <span>Progress</span>
            <strong>{formatNumber(completedCombinations)} / {formatNumber(totalCombinations)}</strong>
            <div className="run-progress-track" aria-label={`${percentComplete}% complete`}>
              <span style={{ width: `${percentComplete}%` }} />
            </div>
            <small>{percentComplete}% complete{failedCombinations ? `, ${failedCombinations} failed` : ""}</small>
          </div>
          <div>
            <span>Status</span>
            <strong>{runStatus}</strong>
            <small>{run?.status === "already_completed" || reusedExistingResult ? "Meridian was not relaunched." : activeChannel ? `Active: ${displayChannelName(activeChannel)}` : isFinalizing(run) ? "Aggregating outputs and preparing dashboard results." : "No active channel reported"}</small>
          </div>
          <div>
            <span>Run source</span>
            <strong>{runSource}</strong>
            <small>{run?.mode === "real_full" ? "Full grid backend launcher" : run?.mode === "real_tiny" ? "Tiny backend launcher" : isDevelopmentMock ? "Development-only control" : "Backend run state"}</small>
          </div>
        </div>
        <div className="run-result-actions">
          {hasResults && resultsUrl ? (
            <Link className="run-open-results" to={resultsUrl}>
              Open Results
            </Link>
          ) : null}
          {run?.status === "completed" || run?.status === "already_completed" ? (
            <Link className="run-browse-results" to="/results/history">
              Browse Saved Results
            </Link>
          ) : null}
        </div>
      </section>

      <section className="content-panel run-timeline-card">
        <h3>Execution Progress</h3>
        <div className="run-timeline">
          {timeline.map((stage, index) => {
            const state = timelineState(run, index);
            return (
              <div className={`run-timeline-step run-timeline-step--${state}`} key={stage.title}>
                <span className="run-timeline-icon">{state === "complete" ? "✓" : index + 1}</span>
                <strong>{stage.title}</strong>
                <small>{stage.time}</small>
                <p>{stage.description}</p>
              </div>
            );
          })}
        </div>
      </section>

      {isFailed ? (
        <section className="run-failure-card">
          <div>
            <strong>Run failed during {timeline[activeStageIndex(run)]?.title.toLowerCase() ?? "execution"}.</strong>
            <span>{run?.messages.slice(-1)[0] ?? "Review the latest logs for backend error details."}</span>
          </div>
          <div className="run-failure-actions">
            <button className="secondary-link" type="button" onClick={() => setShowFullLogs(true)}>View logs</button>
            <Link className="secondary-link" to="/workflow/review-run">Back to Review</Link>
          </div>
        </section>
      ) : null}

      <section className="run-monitor-main-grid">
        <div className="content-panel run-channel-card">
          <div className="section-title-row">
            <div>
              <h3>Channel Progress</h3>
              <p>Results appear as each channel completes.</p>
            </div>
            <span className="subtle-chip">{formatNumber(run?.channel_progress.length ?? 0)} channels</span>
          </div>
          <div className="table-shell">
            <table className="run-channel-table">
              <thead>
                <tr>
                  <th>Channel</th>
                  <th>Status</th>
                  <th>Progress</th>
                  <th>Completed</th>
                  <th>Failed</th>
                  <th>Total</th>
                </tr>
              </thead>
              <tbody>
                {(run?.channel_progress ?? []).map((channel) => {
                  const percent = channelPercent(channel.completedRuns, channel.total_runs);
                  return (
                    <tr key={channel.channel}>
                      <td>
                        <span className="run-channel-name">
                          <ChannelLogo channel={channel.channel} />
                          {displayChannelName(channel.channel)}
                        </span>
                      </td>
                      <td><span className={`run-status-pill run-status-pill--${pillTone(channel.status)}`}>{labelForStatus(channel.status)}</span></td>
                      <td>
                        <div className="run-channel-progress">
                          <span><i style={{ width: `${percent}%` }} /></span>
                          <small>{percent}%</small>
                        </div>
                      </td>
                      <td>{formatNumber(channel.completedRuns)}</td>
                      <td>{formatNumber(channel.failedRuns)}</td>
                      <td>{formatNumber(channel.total_runs)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {!run?.channel_progress.length ? <p className="muted">No channel progress has been reported yet.</p> : null}
        </div>

        <aside className="content-panel run-details-card">
          <h3>Run Details</h3>
          <div className="run-detail-list">
            {detailRows.map(([label, value]) => (
              <div key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
              </div>
            ))}
          </div>
          <div className="run-info-note">
            <span aria-hidden="true">i</span>
            <p>This page reflects the backend run state. Refreshing the page will not restart the run.</p>
          </div>
        </aside>
      </section>

      <section className="content-panel run-activity-card">
        <div className="section-title-row">
          <div>
            <h3>Recent Activity</h3>
          </div>
          <button className="secondary-link run-log-toggle" type="button" onClick={() => setShowFullLogs((current) => !current)}>
            {showFullLogs ? "Hide full logs" : "View full logs"}
          </button>
        </div>
        {activityLines.length ? (
          <ol className="run-activity-list">
            {activityLines.map((line, index) => {
              const lower = line.toLowerCase();
              const activityTimeSource = index === activityLines.length - 1
                ? run?.completed_at || run?.started_at || run?.created_at
                : null;
              const tone = lower.includes("fail") || lower.includes("error")
                ? "failed"
                : lower.includes("start") || lower.includes("running") || lower.includes("stream")
                  ? "running"
                  : lower.includes("queued") || lower.includes("pending")
                    ? "pending"
                    : "complete";
              return (
                <li className={`run-activity-item run-activity-item--${tone}`} key={`${line}-${index}`}>
                  <span>{activityTimeSource ? formatTime(activityTimeSource) : ""}</span>
                  <p>{line}</p>
                </li>
              );
            })}
          </ol>
        ) : (
          <p className="muted">No detailed logs available yet.</p>
        )}
        {showFullLogs ? (
          <pre className="config-preview run-full-log">{logLines.length ? logLines.join("\n") : "No detailed logs available yet."}</pre>
        ) : null}
        {isDevelopmentMock ? (
          <div className="run-dev-controls">
            <strong>Development mock control</strong>
            <button className="primary-action primary-action--enabled" disabled={!run || run.status === "completed" || isAdvancing} type="button" onClick={handleAdvance}>
              {isAdvancing ? "Advancing..." : "Advance Mock Progress"}
            </button>
          </div>
        ) : null}
      </section>
    </article>
  );
}
