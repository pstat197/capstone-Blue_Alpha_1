import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { advanceMockRun, getRunLogs, getRunStatus } from "../../../api/runs";
import type { RunStatus } from "../../../api/types";
import { MetricCard } from "../../results/components/MetricCard";
import { formatNumber } from "../../results/data/resultSelectors";
import { StatusBadge } from "../../workflow/components/StatusBadge";

function statusBadge(status?: string) {
  if (status === "completed") {
    return <StatusBadge status="valid" label="completed" />;
  }
  if (status === "running") {
    return <StatusBadge status="api" label="running" />;
  }
  if (status === "failed" || status === "cancelled") {
    return <StatusBadge status="missing" label={status} />;
  }
  return <StatusBadge status="warning" label={status || "queued"} />;
}

function formatDate(raw?: string | null) {
  if (!raw) {
    return "Not yet";
  }
  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(raw));
}

function elapsedLabel(run: RunStatus | null) {
  if (!run?.started_at) {
    return "Waiting to start";
  }
  const end = run.completed_at ? new Date(run.completed_at).getTime() : Date.now();
  const seconds = Math.max(0, Math.round((end - new Date(run.started_at).getTime()) / 1000));
  return `${seconds}s elapsed`;
}

export function RunMonitorPage() {
  const params = useParams();
  const resolvedRunId = params.runId === "current" ? "demo_32run" : params.runId || "demo_32run";
  const [run, setRun] = useState<RunStatus | null>(null);
  const [logLines, setLogLines] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isAdvancing, setIsAdvancing] = useState(false);

  const loadRun = () => {
    getRunStatus(resolvedRunId)
      .then((status) => {
        setRun(status);
        setError(null);
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
    loadRun();
  }, [resolvedRunId]);

  useEffect(() => {
    if (!run || (run.status !== "queued" && run.status !== "running")) {
      return undefined;
    }
    const timer = window.setInterval(loadRun, 2500);
    return () => window.clearInterval(timer);
  }, [run?.status, resolvedRunId]);

  const percentComplete = useMemo(() => {
    if (!run?.progress.total_runs) {
      return 0;
    }
    return Math.round((run.progress.completed_runs / run.progress.total_runs) * 100);
  }, [run]);
  const isRealRun = run?.mode === "real_tiny" || run?.mode === "real_full";
  const isFullRun = run?.mode === "real_full";

  const handleAdvance = () => {
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

  return (
    <article className="workflow-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">Execution</span>
          <h2>Run Monitor</h2>
        </div>
        <span className="mode-chip mode-chip--execution">{isFullRun ? "full grid execution" : run?.mode === "real_tiny" ? "tiny real execution" : "mock execution"}</span>
      </div>

      <p className="page-summary">
        Track queued, running, completed, or failed run state from the FastAPI store. Real runs stream subprocess logs from the backend launcher.
      </p>

      <section className="source-strip">
        <div>
          <span className="eyebrow">Run source</span>
          <strong>{run ? run.run_id : resolvedRunId}</strong>
          <p>{isRealRun ? "Backend launcher run from API storage." : "API mock run record from backend storage."}</p>
        </div>
        {statusBadge(run?.status)}
      </section>

      {error ? (
        <section className="content-panel">
          <h3>Status unavailable</h3>
          <p className="muted">{error}</p>
        </section>
      ) : null}

      <section className="overview-hero-grid">
        <MetricCard label="Status" value={run?.status || "Loading"} note={`Created ${formatDate(run?.created_at)}`} />
        <MetricCard label="Progress" value={`${formatNumber(run?.progress.completed_runs ?? 0)} / ${formatNumber(run?.progress.total_runs ?? 0)}`} note={`${percentComplete}% complete`} />
        <MetricCard label="Active channel" value={run?.progress.active_target_channel || "None"} note={`mu ${run?.progress.active_mu ?? "-"} / sigma ${run?.progress.active_sigma ?? "-"} / ${run?.progress.active_dist ?? "-"}`} />
        <MetricCard label="Elapsed time" value={elapsedLabel(run)} note="ETA placeholder until structured progress events exist" />
      </section>

      <section className="result-grid">
        <div className="content-panel">
          <div className="section-title-row">
            <div>
              <span className="eyebrow">{isRealRun ? "Launcher status" : "Mock progress control"}</span>
              <h3>{isFullRun ? "Full grid execution" : run?.mode === "real_tiny" ? "Tiny real execution" : "Status transition tester"}</h3>
            </div>
            <StatusBadge status={isRealRun ? "api" : "mock"} label={isRealRun ? "backend" : "simulation"} />
          </div>
          <p className="muted">
            {isFullRun
              ? "The backend is running the full prior-sensitivity grid exactly as configured."
              : run?.mode === "real_tiny"
                ? "The backend is running the one-run Phase 5A pipeline path."
              : "Advance updates local JSON state only. Mock mode remains available for monitor testing."}
          </p>
          {run?.mode === "mock" ? (
            <button className="primary-action primary-action--enabled" disabled={!run || run.status === "completed" || isAdvancing} onClick={handleAdvance}>
              {isAdvancing ? "Advancing..." : "Advance Mock Progress"}
            </button>
          ) : null}
          {run?.result_url ? (
            <Link className="secondary-link" to={run.result_url}>
              Open completed results
            </Link>
          ) : null}
        </div>

        <div className="content-panel">
          <h3>Recent Status Messages</h3>
          <ol className="compact-list">
            {(run?.messages || []).slice(-6).map((message, index) => (
              <li key={`${message}-${index}`}>{message}</li>
            ))}
          </ol>
        </div>
      </section>

      {isRealRun ? (
        <section className="content-panel">
          <div className="section-title-row">
            <div>
              <span className="eyebrow">Run logs</span>
              <h3>Subprocess output</h3>
            </div>
            <span className="subtle-chip">{logLines.length} lines</span>
          </div>
          <pre className="config-preview">{logLines.length ? logLines.join("\n") : "Waiting for launcher logs..."}</pre>
          {run.result_artifacts ? (
            <div className="summary-list">
              <div><strong>output tag</strong><span>{run.output_tag || "Not recorded"}</span></div>
              <div><strong>dashboard payload</strong><span>{String(run.result_artifacts.dashboard_payload || "Not produced")}</span></div>
              <div><strong>report HTML</strong><span>{String(run.result_artifacts.report_html || "Not produced")}</span></div>
              <div><strong>tables directory</strong><span>{String(run.result_artifacts.tables_dir || "Not produced")}</span></div>
              <div><strong>figures directory</strong><span>{String(run.result_artifacts.figures_dir || "Not produced")}</span></div>
            </div>
          ) : null}
        </section>
      ) : null}

      <section className="content-panel">
        <div className="section-title-row">
          <div>
            <span className="eyebrow">Channel progress</span>
              <h3>{isRealRun ? "Backend channel run table" : "Mock target-channel run table"}</h3>
          </div>
          <span className="subtle-chip">{formatNumber(run?.channel_progress.length ?? 0)} channels</span>
        </div>
        <div className="table-shell">
          <table>
            <thead>
              <tr>
                <th>Channel</th>
                <th>Status</th>
                <th>Completed</th>
                <th>Failed</th>
                <th>Total</th>
              </tr>
            </thead>
            <tbody>
              {(run?.channel_progress || []).map((channel) => (
                <tr key={channel.channel}>
                  <td>{channel.channel}</td>
                  <td>{statusBadge(channel.status)}</td>
                  <td>{formatNumber(channel.completedRuns)}</td>
                  <td>{formatNumber(channel.failedRuns)}</td>
                  <td>{formatNumber(channel.total_runs)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </article>
  );
}
