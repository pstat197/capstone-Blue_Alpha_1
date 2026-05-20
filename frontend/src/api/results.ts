import { apiRequest } from "./client";
import type { DashboardPayload } from "../features/results/data/resultTypes";
import type { ResultHistoryPayloadResponse, ResultHistoryResponse, ResultPayloadResponse } from "./types";

export function getResultPayload(runId: string): Promise<ResultPayloadResponse<DashboardPayload>> {
  const cacheBust = Date.now();
  return apiRequest<ResultPayloadResponse<DashboardPayload>>(`/api/runs/${runId}/results/payload?ts=${cacheBust}`, {
    cache: "no-store",
    headers: {
      "Cache-Control": "no-cache",
    },
  });
}

export function getResultHistory(): Promise<ResultHistoryResponse> {
  const cacheBust = Date.now();
  return apiRequest<ResultHistoryResponse>(`/api/results/history?ts=${cacheBust}`, {
    cache: "no-store",
    headers: {
      "Cache-Control": "no-cache",
    },
  });
}

export function getResultHistoryPayload(historyId: string): Promise<ResultHistoryPayloadResponse<DashboardPayload>> {
  const cacheBust = Date.now();
  return apiRequest<ResultHistoryPayloadResponse<DashboardPayload>>(`/api/results/history/${encodeURIComponent(historyId)}?ts=${cacheBust}`, {
    cache: "no-store",
    headers: {
      "Cache-Control": "no-cache",
    },
  });
}
