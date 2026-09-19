import type { ChronicleEvent, ChronicleRecord, InferenceStatusSnapshot, ProjectionStatus, SystemState } from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "http://localhost:8000/api/v1";

const ACCESS_KEY = "creation_access_token";
const REFRESH_KEY = "creation_refresh_token";

function token(): string {
  const value = window.localStorage.getItem(ACCESS_KEY);
  if (!value) throw new Error("AUTH_REQUIRED");
  return value;
}

export function clearSession(): void {
  window.localStorage.removeItem(ACCESS_KEY);
  window.localStorage.removeItem(REFRESH_KEY);
}

let refreshInFlight: Promise<boolean> | null = null;

// Single-flight: refresh tokens are rotated server-side, so concurrent refreshes would revoke each other.
function refreshSession(): Promise<boolean> {
  refreshInFlight ??= (async () => {
    const refreshToken = window.localStorage.getItem(REFRESH_KEY);
    if (!refreshToken) return false;
    try {
      const response = await fetch(`${API_BASE}/auth/refresh`, { method: "POST", headers: { Authorization: `Bearer ${refreshToken}` } });
      if (!response.ok) {
        if (response.status === 401 || response.status === 403) clearSession();
        return false;
      }
      const tokens = await response.json() as TokenResponse;
      window.localStorage.setItem(ACCESS_KEY, tokens.access_token);
      window.localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const send = () => fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { ...init.headers, Authorization: `Bearer ${token()}` },
  });
  let response = await send();
  if (response.status === 401) {
    if (!(await refreshSession())) {
      clearSession();
      throw new Error("AUTH_REQUIRED");
    }
    response = await send();
  }
  if (response.status === 401 || response.status === 403) throw new Error("AUTH_REQUIRED");
  return response;
}

type TokenResponse = {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
};

export type Conversation = {
  id: string;
  creator_id: string;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type ConversationMessage = {
  id: string;
  conversation_id: string;
  actor_id: string;
  role: string;
  content: string;
  route: string;
  metadata_json: Record<string, unknown>;
  correlation_id: string;
  created_at: string;
};

export async function loginCreator(username: string, password: string): Promise<void> {
  const response = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (response.status === 401 || response.status === 403) throw new Error("INVALID_CREDENTIALS");
  if (response.status === 429) throw new Error("RATE_LIMITED");
  if (!response.ok) throw new Error(`HTTP_${response.status}`);
  const tokens = await response.json() as TokenResponse;
  window.localStorage.setItem(ACCESS_KEY, tokens.access_token);
  window.localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  const attempts = method === "GET" ? 3 : 1;
  let lastError: unknown;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const response = await authFetch(path, {
        ...init,
        headers: {
          ...(init?.body ? { "Content-Type": "application/json" } : {}),
          ...init?.headers,
        },
      });
      if (!response.ok) {
        if (response.status < 500 || attempt === attempts - 1) throw new Error(`HTTP_${response.status}`);
        throw new Error(`RETRYABLE_HTTP_${response.status}`);
      }
      return response.json() as Promise<T>;
    } catch (error) {
      if (error instanceof Error && (error.message === "AUTH_REQUIRED" || error.message.startsWith("HTTP_4"))) throw error;
      lastError = error;
      if (attempt < attempts - 1) await new Promise((resolve) => window.setTimeout(resolve, 250 * 2 ** attempt));
    }
  }
  throw lastError instanceof Error ? lastError : new Error("NETWORK_ERROR");
}

export const fetchSystemState = () => api<SystemState>("/system/state");
export const fetchProjectionStatus = () => api<ProjectionStatus>("/system/projections");
export const fetchInferenceStatus = () => api<InferenceStatusSnapshot>("/system/inference");
const CHRONICLE_WINDOW = 40;

// The backend lists Chronicle by ascending position, so page from the tail and return newest first.
export const fetchChronicleHistory = async (head: number): Promise<ChronicleRecord[]> => {
  const offset = Math.max(0, head - CHRONICLE_WINDOW);
  const records = await api<ChronicleRecord[]>(`/chronicles?limit=${CHRONICLE_WINDOW}&offset=${offset}`);
  return records.reverse();
};

export const createConversation = (title = "Creator Session") => api<Conversation>("/conversations", {
  method: "POST",
  body: JSON.stringify({ title }),
});

export const fetchConversationMessages = (conversationId: string) =>
  api<ConversationMessage[]>(`/conversations/${conversationId}/messages`);

export const converseWithDeus = (conversationId: string, content: string) =>
  api<{ response: string }>(`/conversations/${conversationId}/deus`, {
    method: "POST",
    body: JSON.stringify({ content, metadata: {} }),
  });

export type StreamEnd = "closed" | "resync";

// Resolves when the stream ends ("closed" = reconnect from cursor, "resync" = reload state); rejects on failure.
export async function streamChronicle(after: number, onEvent: (event: ChronicleEvent) => void, signal: AbortSignal): Promise<StreamEnd> {
  const response = await authFetch(`/system/events?after=${after}`, { headers: { Accept: "text/event-stream" }, signal });
  if (!response.ok || !response.body) throw new Error(`HTTP_${response.status}`);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (!signal.aborted) {
    const { value, done } = await reader.read();
    if (done) return "closed";
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
      if (eventType === "resync_required") return "resync";
      if (eventType !== "chronicle") continue;
      try {
        onEvent(JSON.parse(data) as ChronicleEvent);
      } catch {
        // Skip a malformed frame instead of dropping the whole stream.
      }
    }
  }
  return "closed";
}
