import type {
  Agent,
  ChronicleEntry,
  Conversation,
  GodResponse,
  Inception,
  Mission,
  Pulse,
  TokenResponse,
  TrinityResponse,
  Universe,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers ?? {}),
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(body.detail ?? response.statusText, response.status);
  }
  return (await response.json()) as T;
}

export const api = {
  baseUrl: API_BASE,

  login(username: string, password: string) {
    return request<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
  },

  createConversation(token: string, title: string) {
    return request<Conversation>(
      "/conversations",
      {
        method: "POST",
        body: JSON.stringify({ title }),
      },
      token,
    );
  },

  sendGod(token: string, conversationId: string, message: string) {
    return request<GodResponse>(
      `/living-core/conversations/${conversationId}/god`,
      {
        method: "POST",
        body: JSON.stringify({
          message,
          idempotency_key: crypto.randomUUID(),
        }),
      },
      token,
    );
  },

  orchestrateTrinity(token: string, godInteractionId: string) {
    return request<TrinityResponse>(
      `/trinity/god-interactions/${godInteractionId}/orchestrate`,
      { method: "POST" },
      token,
    );
  },

  listInceptions(token: string) {
    return request<Inception[]>("/inceptions", undefined, token);
  },

  listMissions(token: string) {
    return request<Mission[]>("/missions", undefined, token);
  },

  listAgents(token: string) {
    return request<Agent[]>("/agents", undefined, token);
  },

  listUniverses(token: string) {
    return request<Universe[]>("/universes", undefined, token);
  },

  listChronicles(token: string) {
    return request<ChronicleEntry[]>("/chronicles?limit=18", undefined, token);
  },

  pulse(token: string) {
    return request<Pulse>("/pulse", undefined, token);
  },
};
