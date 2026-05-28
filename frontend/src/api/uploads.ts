import { API_BASE_URL, apiRequest } from "./client";
import type { CsvPreview, CsvProfile, UploadResponse } from "./types";

export function createUpload(file: File): Promise<UploadResponse> {
  const body = new FormData();
  body.append("file", file);
  return apiRequest<UploadResponse>("/api/uploads", { method: "POST", body });
}

export function loadMonthlyMochaExample(): Promise<UploadResponse> {
  return apiRequest<UploadResponse>("/api/uploads/examples/monthly-mocha", { method: "POST" });
}

export function loadRunnableDemoExample(): Promise<UploadResponse> {
  return apiRequest<UploadResponse>("/api/uploads/examples/runnable-demo", { method: "POST" });
}

export const blankCsvTemplateUrl = `${API_BASE_URL}/api/uploads/templates/blank`;
export const schemaPreviewCsvUrl = `${API_BASE_URL}/api/uploads/examples/schema-preview`;
export const runnableDemoCsvUrl = `${API_BASE_URL}/api/uploads/examples/runnable-demo`;

export function getUploadProfile(uploadId: string): Promise<CsvProfile> {
  return apiRequest<CsvProfile>(`/api/uploads/${uploadId}/profile`);
}

export function getUploadPreview(uploadId: string, limit = 10): Promise<CsvPreview> {
  return apiRequest<CsvPreview>(`/api/uploads/${uploadId}/preview?limit=${limit}`);
}
