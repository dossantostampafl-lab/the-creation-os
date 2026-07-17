import type {
  Agent,
  AutomationExecution,
  CapabilityFramework,
  ChronicleEntry,
  Conversation,
  CreatorNotification,
  GodResponse,
  Inception,
  Mission,
  MissionManifestation,
  Opportunity,
  PerceptionRun,
  PerceptionRunResult,
  PerceptionSource,
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

  getMissionManifestation(token: string, missionId: string) {
    return request<MissionManifestation>(`/malkuth/missions/${missionId}/manifestation`, undefined, token);
  },

  listCapabilities(token: string) {
    return request<CapabilityFramework[]>("/automation/capabilities", undefined, token);
  },

  enableCapability(token: string, capabilityId: string) {
    return request<CapabilityFramework>(
      `/automation/capabilities/${encodeURIComponent(capabilityId)}/enable`,
      { method: "POST" },
      token,
    );
  },

  disableCapability(token: string, capabilityId: string) {
    return request<CapabilityFramework>(
      `/automation/capabilities/${encodeURIComponent(capabilityId)}/disable`,
      { method: "POST" },
      token,
    );
  },

  executeAutomation(
    token: string,
    body: {
      connector_id: string;
      capability: string;
      payload: Record<string, unknown>;
      timeout_seconds: number;
      idempotency_key: string;
    },
  ) {
    return request<AutomationExecution>(
      "/automation/execute",
      {
        method: "POST",
        body: JSON.stringify(body),
      },
      token,
    );
  },

  listOpportunities(token: string) {
    return request<Opportunity[]>("/opportunities/ranking?limit=8", undefined, token);
  },

  runOpportunityDiscovery(token: string) {
    return request<{ opportunities: Opportunity[] }>(
      "/opportunities/discovery/run",
      {
        method: "POST",
        body: JSON.stringify({
          observations: [
            {
              universe: "finance",
              source: "fixture.market",
              subject: "ACME",
              event_type: "volume_anomaly",
              title: "ACME volume anomaly",
              summary: "Volume rose above the configured informational threshold.",
              source_reliability: 0.82,
              correlation_key: "acme:volume",
              normalized_data: { percent_change: 8.4, volume_ratio: 2.7 },
              evidence: { type: "controlled_fixture", financial_execution: false },
            },
            {
              universe: "technology",
              source: "fixture.trends",
              subject: "Deterministic Agents",
              event_type: "launch",
              title: "Deterministic agent tooling launch",
              summary: "Multiple technical sources indicate rising interest in deterministic agent tooling.",
              source_reliability: 0.76,
              correlation_key: "deterministic-agents:launch",
              normalized_data: { activity_growth: 0.68 },
              evidence: { type: "controlled_fixture" },
            },
          ],
        }),
      },
      token,
    );
  },

  approveOpportunity(token: string, opportunityId: string) {
    return request<Opportunity>(
      `/opportunities/${opportunityId}/approve`,
      {
        method: "POST",
        body: JSON.stringify({ reason: "Creator approved investigation." }),
      },
      token,
    );
  },

  rejectOpportunity(token: string, opportunityId: string) {
    return request<Opportunity>(
      `/opportunities/${opportunityId}/reject`,
      {
        method: "POST",
        body: JSON.stringify({ reason: "Creator rejected the opportunity." }),
      },
      token,
    );
  },

  convertOpportunity(token: string, opportunityId: string) {
    return request<Opportunity>(`/opportunities/${opportunityId}/convert-to-inception`, { method: "POST" }, token);
  },

  listPerceptionSources(token: string) {
    return request<PerceptionSource[]>("/perception/sources", undefined, token);
  },

  enablePerceptionSource(token: string, sourceId: string) {
    return request<PerceptionSource>(`/perception/sources/${sourceId}/enable`, { method: "POST" }, token);
  },

  disablePerceptionSource(token: string, sourceId: string) {
    return request<PerceptionSource>(`/perception/sources/${sourceId}/disable`, { method: "POST" }, token);
  },

  runPerceptionSource(token: string, sourceId: string) {
    return request<PerceptionRunResult>(`/perception/sources/${sourceId}/run`, { method: "POST" }, token);
  },

  listPerceptionRuns(token: string, sourceId: string) {
    return request<PerceptionRun[]>(`/perception/sources/${sourceId}/runs?limit=8`, undefined, token);
  },

  listNotifications(token: string) {
    return request<CreatorNotification[]>("/notifications?limit=20", undefined, token);
  },

  readNotification(token: string, notificationId: string) {
    return request<CreatorNotification>(`/notifications/${notificationId}/read`, { method: "POST" }, token);
  },

  acknowledgeNotification(token: string, notificationId: string) {
    return request<CreatorNotification>(`/notifications/${notificationId}/acknowledge`, { method: "POST" }, token);
  },
};
