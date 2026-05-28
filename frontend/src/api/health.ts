import { apiRequest } from "./client";
import type { HealthResponse } from "./types";

export function getHealth(): Promise<HealthResponse> {
  return apiRequest<HealthResponse>("/api/health");
}
