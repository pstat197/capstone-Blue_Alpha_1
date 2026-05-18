import { useEffect, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { getResultPayload } from "../../../api/results";
import { getLatestCompletedRun, getRunStatus } from "../../../api/runs";
import type { RunStatus } from "../../../api/types";
import { resultNavItems } from "../../../app/navigation";
import { activeRunIdStorageKey } from "../../workflow/data/workflowState";
import type { DashboardPayload } from "./resultTypes";

export type ResultSourceKind = "api" | "loading" | "missing" | "error";

export type ResultDataSource = {
  id: string;
  activeRunId: string | null;
  label: string;
  sourceKind: ResultSourceKind;
  sourceLabel: string;
  sourceDetail: string;
  payload: DashboardPayload;
  assetBasePath: string;
  assets: {
    roiPriorPosteriorFigure: string;
  };
  runSummary: RunStatus | null;
  buildResultsPath: (pathOrSlug: string) => string;
  error?: string;
};

export type ActiveResultsRun = {
  activeRunId: string | null;
  runSummary: RunStatus | null;
  loading: boolean;
  error: string | null;
  buildResultsPath: (pathOrSlug: string) => string;
};

const activeResultsRunStorageKey = `${activeRunIdStorageKey}.results`;

function readStoredActiveRunId(): string | null {
  return (
    window.sessionStorage.getItem(activeResultsRunStorageKey)?.trim() ||
    window.localStorage.getItem(activeResultsRunStorageKey)?.trim() ||
    window.sessionStorage.getItem(activeRunIdStorageKey)?.trim() ||
    window.localStorage.getItem(activeRunIdStorageKey)?.trim() ||
    null
  );
}

export function writeActiveResultsRunId(runId: string) {
  window.sessionStorage.setItem(activeRunIdStorageKey, runId);
  window.localStorage.setItem(activeRunIdStorageKey, runId);
  window.sessionStorage.setItem(activeResultsRunStorageKey, runId);
  window.localStorage.setItem(activeResultsRunStorageKey, runId);
}

export function readActiveResultsRunId(): string | null {
  return readStoredActiveRunId();
}

export function buildResultsPath(pathOrSlug: string, runId?: string | null): string {
  const basePath = pathOrSlug.startsWith("/results/")
    ? pathOrSlug
    : resultNavItems.find((item) => item.path.endsWith(`/${pathOrSlug}`))?.path || `/results/${pathOrSlug}`;
  return runId ? `${basePath}?run_id=${encodeURIComponent(runId)}` : basePath;
}

function emptyResult(runId: string, sourceKind: ResultSourceKind, message: string): ResultDataSource {
  return {
    id: runId || "unselected",
    activeRunId: runId || null,
    label: runId ? `Run ${runId}` : "No run selected",
    sourceKind,
    sourceLabel: runId ? `Run ${runId}` : "No run selected",
    sourceDetail: message,
    payload: {},
    assetBasePath: "",
    assets: {
      roiPriorPosteriorFigure: "",
    },
    runSummary: null,
    buildResultsPath: (pathOrSlug: string) => buildResultsPath(pathOrSlug, runId || null),
    error: message,
  };
}

export function useActiveResultsRun(): ActiveResultsRun {
  const params = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const queryRunId = new URLSearchParams(location.search).get("run_id")?.trim() || null;
  const routeRunId = params.runId?.trim() || null;
  const initialRunId = queryRunId || routeRunId || readStoredActiveRunId();
  const [activeRunId, setActiveRunId] = useState<string | null>(initialRunId);
  const [runSummary, setRunSummary] = useState<RunStatus | null>(null);
  const [loading, setLoading] = useState(!initialRunId);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const persistAndReflect = (runId: string) => {
      writeActiveResultsRunId(runId);
      if (!queryRunId && location.pathname.startsWith("/results/")) {
        const search = new URLSearchParams(location.search);
        search.set("run_id", runId);
        navigate(`${location.pathname}?${search.toString()}`, { replace: true });
      }
    };

    const loadLatestCompleted = () => {
      setLoading(true);
      getLatestCompletedRun()
        .then((latest) => {
          if (cancelled) return;
          persistAndReflect(latest.run_id);
          setActiveRunId(latest.run_id);
          setRunSummary(latest);
          setError(null);
        })
        .catch((latestError: unknown) => {
          if (cancelled) return;
          setActiveRunId(null);
          setRunSummary(null);
          setError(latestError instanceof Error ? latestError.message : "No completed backend run is available.");
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    };

    const requestedRunId = queryRunId || routeRunId || readStoredActiveRunId();
    if (!requestedRunId) {
      loadLatestCompleted();
      return () => {
        cancelled = true;
      };
    }

    setActiveRunId(requestedRunId);
    persistAndReflect(requestedRunId);
    setLoading(true);
    getRunStatus(requestedRunId)
      .then((status) => {
        if (cancelled) return;
        if (status.status === "completed") {
          persistAndReflect(status.run_id);
        }
        setRunSummary(status);
        setError(null);
      })
      .catch(() => {
        if (!cancelled) loadLatestCompleted();
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [location.pathname, location.search, navigate, queryRunId, routeRunId]);

  return {
    activeRunId,
    runSummary,
    loading,
    error,
    buildResultsPath: (pathOrSlug: string) => buildResultsPath(pathOrSlug, activeRunId),
  };
}

export function useCurrentResult(): ResultDataSource {
  const activeResultsRun = useActiveResultsRun();
  const requestedRunId = activeResultsRun.activeRunId || "";
  const [result, setResult] = useState<ResultDataSource>(() =>
    emptyResult(requestedRunId, requestedRunId || activeResultsRun.loading ? "loading" : "missing", "Loading result payload.")
  );

  useEffect(() => {
    let cancelled = false;

    if (!requestedRunId) {
      setResult(
        emptyResult(
          "",
          activeResultsRun.loading ? "loading" : "missing",
          activeResultsRun.loading
            ? "Resolving the active completed run."
            : "Results are not selected because no completed run could be resolved."
        )
      );
      return () => {
        cancelled = true;
      };
    }

    setResult(emptyResult(requestedRunId, "loading", "Loading result payload."));

    getResultPayload(requestedRunId)
      .then((response) => {
        if (cancelled) {
          return;
        }
        setResult({
          id: response.run_id,
          activeRunId: response.run_id,
          label: `Run ${response.run_id}`,
          sourceKind: "api",
          sourceLabel: `Run ${response.run_id}`,
          sourceDetail: response.output_tag
            ? `${response.source || "Backend"} artifact: ${response.output_tag}.`
            : `${response.source || "Backend"} artifact loaded for this run.`,
          payload: response.payload,
          assetBasePath: "",
          assets: {
            roiPriorPosteriorFigure: "",
          },
          runSummary: activeResultsRun.runSummary,
          buildResultsPath: activeResultsRun.buildResultsPath,
        });
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        const message = error instanceof Error ? error.message : "FastAPI result payload unavailable.";
        setResult(emptyResult(requestedRunId, "error", `Results are not available for this run yet. Please check whether dashboard artifacts were generated. ${message}`));
      });

    return () => {
      cancelled = true;
    };
  }, [activeResultsRun.loading, activeResultsRun.runSummary, requestedRunId]);

  return {
    ...result,
    activeRunId: requestedRunId || result.activeRunId,
    runSummary: activeResultsRun.runSummary || result.runSummary,
    buildResultsPath: activeResultsRun.buildResultsPath,
  };
}
