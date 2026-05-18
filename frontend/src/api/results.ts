import { apiRequest } from "./client";
import type { DashboardPayload } from "../features/results/data/resultTypes";
import type { ResultPayloadResponse } from "./types";

export function getResultPayload(runId: string): Promise<ResultPayloadResponse<DashboardPayload>> {
  const cacheBust = Date.now();
  return apiRequest<ResultPayloadResponse<DashboardPayload>>(`/api/runs/${runId}/results/payload?ts=${cacheBust}`, {
    cache: "no-store",
    headers: {
      "Cache-Control": "no-cache",
    },
  });
}
