export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: init?.body instanceof FormData
      ? init.headers
      : {
          "Content-Type": "application/json",
          ...init?.headers,
        },
  });

  if (!response.ok) {
    const detail = await response.text();
    let message = detail;
    try {
      const parsed = JSON.parse(detail) as { detail?: unknown };
      message = typeof parsed.detail === "string" ? parsed.detail : detail;
    } catch {
      message = detail;
    }
    throw new Error(`API request failed (${response.status}): ${message}`);
  }

  return response.json() as Promise<T>;
}
