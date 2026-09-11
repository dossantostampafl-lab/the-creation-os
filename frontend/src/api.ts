import type { ChronicleEvent, ChronicleRecord, InferenceStatusSnapshot, ProjectionStatus, SystemState } from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "http://localhost:8000/api/v1";

function token(): string {
  const value = window.localStorage.getItem("creation_access_token");
  if (!value) throw new Error("AUTH_REQUIRED");
  return value;
}

type TokenResponse = {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
};

export async function loginCreator(username: string, password: string): Promise<void> {
  const response = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (response.status === 401 || response.status === 403) throw new Error("INVALID_CREDENTIALS");
  if (!response.ok) throw new Error(`HTTP_${response.status}`);
  const tokens = await response.json() as TokenResponse;
  window.localStorage.setItem("creation_access_token", tokens.access_token);
  window.localStorage.setItem("creation_refresh_token", tokens.refresh_token);
}

async function api<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${token()}` },
  });
  if (response.status === 401 || response.status === 403) throw new Error("AUTH_REQUIRED");
  if (!response.ok) throw new Error(`HTTP_${response.status}`);
  return response.json() as Promise<T>;
}

export const fetchSystemState = () => api<SystemState>("/system/state");
export const fetchProjectionStatus = () => api<ProjectionStatus>("/system/projections");
export const fetchInferenceStatus = () => api<InferenceStatusSnapshot>("/system/inference");
export const fetchChronicleHistory = () => api<ChronicleRecord[]>("/chronicles?limit=40&offset=0");

export type StreamHandlers = {
  onEvent: (event: ChronicleEvent) => void;
  onResync: () => void;
  onError: (error: unknown) => void;
};

export async function streamChronicle(after: number, handlers: StreamHandlers, signal: AbortSignal): Promise<void> {
  try {
    const response = await fetch(`${API_BASE}/system/events?after=${after}`, {
      headers: { Authorization: `Bearer ${token()}`, Accept: "text/event-stream" },
      signal,
    });
    if (response.status === 401 || response.status === 403) throw new Error("AUTH_REQUIRED");
    if (!response.ok || !response.body) throw new Error(`HTTP_${response.status}`);

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (!signal.aborted) {
      const { value, done } = await reader.read();
      if (done) return;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";

      for (const frame of frames) {
        if (!frame || frame.startsWith(":")) continue;
        let eventType = "message";
        let data = "";
        for (const line of frame.split("\n")) {
          if (line.startsWith("event:")) eventType = line.slice(6).trim();
          if (line.startsWith("data:")) data += line.slice(5).trim();
        }
        if (!data) continue;
        if (eventType === "resync_required") {
          handlers.onResync();
          return;
        }
        if (eventType === "chronicle") handlers.onEvent(JSON.parse(data) as ChronicleEvent);
      }
    }
  } catch (error) {
    if (!signal.aborted) handlers.onError(error);
  }
}
