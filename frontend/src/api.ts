import type { ChronicleEvent, ProjectionStatus, Session, SystemState } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function parseError(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    return payload.detail ?? response.statusText;
  } catch {
    return response.statusText;
  }
}

async function request<T>(path: string, token?: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!response.ok) throw new ApiError(response.status, await parseError(response));
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function login(username: string, password: string): Promise<Session> {
  const payload = await request<{ access_token: string; refresh_token: string; expires_in: number }>(
    "/api/v1/auth/login",
    undefined,
    { method: "POST", body: JSON.stringify({ username, password }) },
  );
  return {
    accessToken: payload.access_token,
    refreshToken: payload.refresh_token,
    expiresIn: payload.expires_in,
  };
}

export const getSystemState = (token: string) => request<SystemState>("/api/v1/system/state", token);
export const getProjectionStatus = (token: string) => request<ProjectionStatus>("/api/v1/system/projections", token);

export async function streamChronicle(
  token: string,
  after: number,
  signal: AbortSignal,
  onEvent: (event: ChronicleEvent) => void,
  onResync: (reason: Record<string, unknown>) => void,
): Promise<void> {
  const response = await fetch(`${API_BASE}/api/v1/system/events?after=${after}`, {
    headers: { Accept: "text/event-stream", Authorization: `Bearer ${token}` },
    signal,
  });
  if (!response.ok || !response.body) {
    throw new ApiError(response.status, await parseError(response));
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (!signal.aborted) {
    const { done, value } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf("\n\n");
      if (!frame || frame.startsWith(":")) continue;

      let eventName = "message";
      let data = "";
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue;
      const payload = JSON.parse(data);
      if (eventName === "chronicle") onEvent(payload as ChronicleEvent);
      if (eventName === "resync_required") onResync(payload as Record<string, unknown>);
    }
  }
}
