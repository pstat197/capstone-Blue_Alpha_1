import { apiRequest } from "./client";
import type { DashboardPayload } from "../features/results/data/resultTypes";
import type { ResultPayloadResponse } from "./types";

export function getResultPayload(runId = "demo_32run"): Promise<ResultPayloadResponse<DashboardPayload>> {
  return apiRequest<ResultPayloadResponse<DashboardPayload>>(`/api/runs/${runId}/results/payload`);
}
