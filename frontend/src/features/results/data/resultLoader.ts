import { useEffect, useState } from "react";
import demoPayload from "../../../../../data/output/03_reports/report/demo_32run/tables/dashboard_payload.json";
import roiPriorPosteriorFigure from "../../../../../data/output/03_reports/report/demo_32run/figures/roi_prior_vs_posterior.png";
import { getResultPayload } from "../../../api/results";
import type { DashboardPayload } from "./resultTypes";

export type ResultSourceKind = "api" | "bundled" | "error";

export type ResultDataSource = {
  id: string;
  label: string;
  sourceKind: ResultSourceKind;
  sourceLabel: string;
  sourceDetail: string;
  payload: DashboardPayload;
  assetBasePath: string;
  assets: {
    roiPriorPosteriorFigure: string;
  };
  error?: string;
};

export function loadCurrentResult(): ResultDataSource {
  return {
    id: "demo_32run",
    label: "Demo 32-run generated output",
    sourceKind: "bundled",
    sourceLabel: "Demo 32-run generated output",
    sourceDetail: "Generated report payload and figures for the sample analysis.",
    payload: demoPayload as DashboardPayload,
    assetBasePath: "/data/output/03_reports/report/demo_32run",
    assets: {
      roiPriorPosteriorFigure,
    },
  };
}

export function useCurrentResult(): ResultDataSource {
  const [result, setResult] = useState<ResultDataSource>(() => loadCurrentResult());
  const requestedRunId = new URLSearchParams(window.location.search).get("run_id") || "demo_32run";
  const isDemoRun = requestedRunId === "demo_32run";

  useEffect(() => {
    let cancelled = false;

    getResultPayload(requestedRunId)
      .then((response) => {
        if (cancelled) {
          return;
        }
        setResult({
          ...loadCurrentResult(),
          id: response.run_id,
          sourceKind: "api",
          sourceLabel: `Run ${response.run_id}`,
          sourceDetail: "Generated report payload and figures for this analysis.",
          payload: response.payload,
        });
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        const message = error instanceof Error ? error.message : "FastAPI result payload unavailable.";
        if (!isDemoRun) {
          setResult({
            id: requestedRunId,
            label: `Run ${requestedRunId}`,
            sourceKind: "error",
            sourceLabel: `Run ${requestedRunId}`,
            sourceDetail: `Result payload unavailable: ${message}`,
            payload: {},
            assetBasePath: "",
            assets: {
              roiPriorPosteriorFigure: "",
            },
            error: message,
          });
          return;
        }
        setResult({
          ...loadCurrentResult(),
          error: message,
        });
      });

    return () => {
      cancelled = true;
    };
  }, [requestedRunId, isDemoRun]);

  return result;
}
