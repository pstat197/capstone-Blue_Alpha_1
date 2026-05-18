import { apiRequest } from "./client";
import type { RunCreateRequest, RunLogsResponse, RunStatus } from "./types";

export function createMockRun(request: RunCreateRequest): Promise<RunStatus> {
  return apiRequest<RunStatus>("/api/runs", {
    method: "POST",
    body: JSON.stringify({ ...request, mode: "mock" }),
  });
}

export function createTinyRealRun(request: RunCreateRequest): Promise<RunStatus> {
  return apiRequest<RunStatus>("/api/runs", {
    method: "POST",
    body: JSON.stringify({ ...request, mode: "real_tiny" }),
  });
}

export function createFullGridRun(request: RunCreateRequest): Promise<RunStatus> {
  return apiRequest<RunStatus>("/api/runs", {
    method: "POST",
    body: JSON.stringify({ ...request, mode: "real_full" }),
  });
}

export function getRunStatus(runId: string): Promise<RunStatus> {
  return apiRequest<RunStatus>(`/api/runs/${runId}`);
}

export function getLatestCompletedRun(): Promise<RunStatus> {
  return apiRequest<RunStatus>("/api/runs/latest-completed");
}

export function advanceMockRun(runId: string): Promise<RunStatus> {
  return apiRequest<RunStatus>(`/api/runs/${runId}/mock/advance`, {
    method: "POST",
  });
}

export function getRunLogs(runId: string): Promise<RunLogsResponse> {
  return apiRequest<RunLogsResponse>(`/api/runs/${runId}/logs`);
}
