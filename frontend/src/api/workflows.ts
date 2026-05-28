import { apiRequest } from "./client";
import type { ConfigPreview, WorkflowDraft, WorkflowDraftRequest } from "./types";

export function createWorkflowDraft(request: WorkflowDraftRequest): Promise<WorkflowDraft> {
  return apiRequest<WorkflowDraft>("/api/workflows", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function getWorkflowDraft(workflowId: string): Promise<WorkflowDraft> {
  return apiRequest<WorkflowDraft>(`/api/workflows/${workflowId}`);
}

export function patchWorkflowDraft(workflowId: string, request: WorkflowDraftRequest): Promise<WorkflowDraft> {
  return apiRequest<WorkflowDraft>(`/api/workflows/${workflowId}`, {
    method: "PATCH",
    body: JSON.stringify(request),
  });
}

export function previewWorkflowConfig(workflowId: string): Promise<ConfigPreview> {
  return apiRequest<ConfigPreview>(`/api/workflows/${workflowId}/config/preview`, {
    method: "POST",
  });
}
