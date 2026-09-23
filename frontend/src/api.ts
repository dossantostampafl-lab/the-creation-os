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
  if (!response.ok) throw new Error(`HTTP_${response.status}`);
  const tokens = await response.json() as TokenResponse;
  window.localStorage.setItem("creation_access_token", tokens.access_token);
  window.localStorage.setItem("creation_refresh_token", tokens.refresh_token);
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  const attempts = method === "GET" ? 3 : 1;
  let lastError: unknown;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const response = await fetch(`${API_BASE}${path}`, {
        ...init,
        headers: {
          Authorization: `Bearer ${token()}`,
          ...(init?.body ? { "Content-Type": "application/json" } : {}),
          ...init?.headers,
        },
      });
      if (response.status === 401 || response.status === 403) throw new Error("AUTH_REQUIRED");
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
export const fetchChronicleHistory = () => api<ChronicleRecord[]>("/chronicles?limit=40&offset=0");

export const createConversation = (title = "Creator Session") => api<Conversation>("/conversations", {
  method: "POST",
  body: JSON.stringify({ title }),
});

export const fetchConversationMessages = (conversationId: string) =>
  api<ConversationMessage[]>(`/conversations/${conversationId}/messages`);

export type ProposalSummary = { id: string; title: string; status: string; verdict: string };

export const converseWithDeus = (conversationId: string, content: string) =>
  api<{ response: string; inception: ProposalSummary | null }>(`/conversations/${conversationId}/deus`, {
    method: "POST",
    body: JSON.stringify({ content, metadata: {} }),
  });

/** What SOPHIA and ROCKMAM concluded about a Creator request (empty for hand-made Inceptions). */
export type TrinityAssessment = {
  sophia?: { opportunities: string[]; risks: string[]; recommendation: string };
  rockmam?: { objective: string; constraints: string[]; completion_criteria: string[] };
  mission_plan?: { strategy: string; steps: Array<{ step_key: string; title: string; universe: string; position: number }> };
  verdict?: { result: "VIABLE" | "REQUIRES_CREATOR"; unavailable_universes: string[] };
};

export type Inception = {
  id: string;
  conversation_id: string;
  title: string;
  description: string;
  status: string;
  trinity_assessment: TrinityAssessment;
  proposed_at: string;
};

export const fetchInceptions = () => api<Inception[]>("/inceptions");
export const fetchInception = (id: string) => api<Inception>(`/inceptions/${id}`);

export const decideInception = (id: string, decision: "approve" | "reject") =>
  api<Inception>(`/inceptions/${id}/${decision}`, { method: "POST", body: JSON.stringify({}) });

/** DEUS voice through the backend's ElevenLabs proxy; the provider key never reaches the browser. */
export async function synthesizeVoice(text: string, signal?: AbortSignal): Promise<Blob> {
  const response = await fetch(`${API_BASE}/voice/synthesize`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token()}`, "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
    signal,
  });
  if (response.status === 401 || response.status === 403) throw new Error("AUTH_REQUIRED");
  if (!response.ok) throw new Error(`HTTP_${response.status}`);
  const audio = await response.blob();
  if (!audio.size || !audio.type.startsWith("audio/")) throw new Error("VOICE_INVALID_AUDIO");
  return audio;
}

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
