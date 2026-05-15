import { apiRequest } from "./client";
import type { CsvPreview, CsvProfile, UploadResponse } from "./types";

export function createUpload(file: File): Promise<UploadResponse> {
  const body = new FormData();
  body.append("file", file);
  return apiRequest<UploadResponse>("/api/uploads", { method: "POST", body });
}

export function loadMonthlyMochaExample(): Promise<UploadResponse> {
  return apiRequest<UploadResponse>("/api/uploads/examples/monthly-mocha", { method: "POST" });
}

export function getUploadProfile(uploadId: string): Promise<CsvProfile> {
  return apiRequest<CsvProfile>(`/api/uploads/${uploadId}/profile`);
}

export function getUploadPreview(uploadId: string, limit = 10): Promise<CsvPreview> {
  return apiRequest<CsvPreview>(`/api/uploads/${uploadId}/preview?limit=${limit}`);
}
