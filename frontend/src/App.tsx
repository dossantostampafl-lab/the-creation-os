import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "./api";
import { CapabilityPanel } from "./components/CapabilityPanel";
import { ChronicleRibbon } from "./components/ChronicleRibbon";
import { GodChat } from "./components/GodChat";
import { InceptionPanel } from "./components/InceptionPanel";
import { LivingUniverse } from "./components/LivingUniverse";
import { PulseHeader } from "./components/PulseHeader";
import type {
  Agent,
  AutomationExecution,
  CapabilityFramework,
  ChatItem,
  ChronicleEntry,
  Conversation,
  Inception,
  Mission,
  MissionManifestation,
  Pulse,
  Universe,
} from "./types";

type LoadState = "idle" | "loading" | "ready" | "empty" | "error";

const REFRESH_INTERVAL_MS = 15000;
const WORKSPACE_CACHE_KEY = "creator-interface-workspace-cache";

type WorkspaceCache = {
  inceptions: Inception[];
  missions: Mission[];
  agents: Agent[];
  universes: Universe[];
  chronicles: ChronicleEntry[];
  manifestations: MissionManifestation[];
  capabilities: CapabilityFramework[];
  pulse: Pulse | null;
};

function normalizeStatus(value: string) {
  return value.toLowerCase();
}

function pendingInception(item: Inception) {
  return !["approved", "rejected", "cancelled"].includes(normalizeStatus(item.status));
}

export function App() {
  const [username] = useState("creator");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState<string | null>(localStorage.getItem("creator-token"));
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [chat, setChat] = useState<ChatItem[]>([
    { id: "intro", role: "god", text: "GOD esta presente. Aguardando a palavra do Criador.", meta: "local" },
  ]);
  const [message, setMessage] = useState("");
  const [inceptions, setInceptions] = useState<Inception[]>([]);
  const [missions, setMissions] = useState<Mission[]>([]);
  const [manifestations, setManifestations] = useState<MissionManifestation[]>([]);
  const [capabilities, setCapabilities] = useState<CapabilityFramework[]>([]);
  const [automationResult, setAutomationResult] = useState<AutomationExecution | null>(null);
  const [capabilityError, setCapabilityError] = useState<string | null>(null);
  const [capabilityBusy, setCapabilityBusy] = useState(false);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [universes, setUniverses] = useState<Universe[]>([]);
  const [chronicles, setChronicles] = useState<ChronicleEntry[]>([]);
  const [pulse, setPulse] = useState<Pulse | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [dataError, setDataError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const authenticated = Boolean(token);
  const activeAgents = useMemo(() => agents.filter((agent) => agent.enabled), [agents]);
  const visibleInceptions = inceptions.filter(pendingInception);
  const empty = loadState === "empty";

  useEffect(() => {
    if (!token) {
      setLoadState("idle");
      return undefined;
    }
    restoreWorkspaceCache();
    void refreshWorkspace(token, true);
    const interval = window.setInterval(() => {
      void refreshWorkspace(token, false);
    }, REFRESH_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [token]);

  function restoreWorkspaceCache() {
    const cached = localStorage.getItem(WORKSPACE_CACHE_KEY);
    if (!cached) return;
    try {
      const workspace = JSON.parse(cached) as WorkspaceCache;
      setInceptions(workspace.inceptions ?? []);
      setMissions(workspace.missions ?? []);
      setAgents(workspace.agents ?? []);
      setUniverses(workspace.universes ?? []);
      setChronicles(workspace.chronicles ?? []);
      setManifestations(workspace.manifestations ?? []);
      setCapabilities(workspace.capabilities ?? []);
      setPulse(workspace.pulse ?? null);
    } catch {
      localStorage.removeItem(WORKSPACE_CACHE_KEY);
    }
  }

  function cacheWorkspace(workspace: WorkspaceCache) {
    localStorage.setItem(WORKSPACE_CACHE_KEY, JSON.stringify(workspace));
  }

  async function refreshWorkspace(accessToken: string, showLoading: boolean) {
    if (showLoading) setLoadState("loading");
    setDataError(null);
    const [loadedInceptions, loadedMissions, loadedAgents, loadedUniverses, loadedChronicles, loadedPulse, loadedCapabilities] =
      await Promise.allSettled([
        api.listInceptions(accessToken),
        api.listMissions(accessToken),
        api.listAgents(accessToken),
        api.listUniverses(accessToken),
        api.listChronicles(accessToken),
        api.pulse(accessToken),
        api.listCapabilities(accessToken),
      ]);

    const failures = [
      loadedInceptions,
      loadedMissions,
      loadedAgents,
      loadedUniverses,
      loadedChronicles,
      loadedPulse,
      loadedCapabilities,
    ].filter((result) => result.status === "rejected");

    const nextInceptions = loadedInceptions.status === "fulfilled" ? loadedInceptions.value : inceptions;
    const nextMissions = loadedMissions.status === "fulfilled" ? loadedMissions.value : missions;
    const nextAgents = loadedAgents.status === "fulfilled" ? loadedAgents.value : agents;
    const nextUniverses = loadedUniverses.status === "fulfilled" ? loadedUniverses.value : universes;
    const nextChronicles = loadedChronicles.status === "fulfilled" ? loadedChronicles.value : chronicles;
    const nextPulse = loadedPulse.status === "fulfilled" ? loadedPulse.value : pulse;
    const nextCapabilities = loadedCapabilities.status === "fulfilled" ? loadedCapabilities.value : capabilities;

    const manifestationResults = await Promise.allSettled(
      nextMissions.map((mission) => api.getMissionManifestation(accessToken, mission.id)),
    );
    const nextManifestations = manifestationResults.flatMap((result) => (result.status === "fulfilled" ? [result.value] : []));

    setInceptions(nextInceptions);
    setMissions(nextMissions);
    setAgents(nextAgents);
    setUniverses(nextUniverses);
    setChronicles(nextChronicles);
    setPulse(nextPulse);
    setManifestations(nextManifestations);
    setCapabilities(nextCapabilities);

    if (failures.length > 0) {
      setLoadState("error");
      setDataError("Falha ao carregar dados reais da API.");
      return;
    }

    const hasData =
      loadedInceptions.status === "fulfilled" &&
      loadedMissions.status === "fulfilled" &&
      loadedAgents.status === "fulfilled" &&
      loadedUniverses.status === "fulfilled" &&
      loadedChronicles.status === "fulfilled" &&
      loadedCapabilities.status === "fulfilled" &&
      (loadedInceptions.value.length > 0 ||
        loadedMissions.value.length > 0 ||
        loadedAgents.value.length > 0 ||
        loadedUniverses.value.length > 0 ||
        loadedChronicles.value.length > 0 ||
        loadedCapabilities.value.length > 0 ||
        nextManifestations.length > 0);
    cacheWorkspace({
      inceptions: nextInceptions,
      missions: nextMissions,
      agents: nextAgents,
      universes: nextUniverses,
      chronicles: nextChronicles,
      manifestations: nextManifestations,
      capabilities: nextCapabilities,
      pulse: nextPulse,
    });
    setLoadState(hasData ? "ready" : "empty");
  }

  async function handleLogin(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const result = await api.login(username, password);
      localStorage.setItem("creator-token", result.access_token);
      setToken(result.access_token);
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  async function ensureConversation(accessToken: string) {
    if (conversation) return conversation;
    const created = await api.createConversation(accessToken, "Creator Interface");
    setConversation(created);
    return created;
  }

  async function handleEnableCapability(capabilityId: string) {
    if (!token) return;
    setCapabilityBusy(true);
    setCapabilityError(null);
    try {
      await api.enableCapability(token, capabilityId);
      await refreshWorkspace(token, false);
    } catch (error) {
      setCapabilityError(error instanceof ApiError ? error.message : "Falha ao habilitar capability.");
    } finally {
      setCapabilityBusy(false);
    }
  }

  async function handleDisableCapability(capabilityId: string) {
    if (!token) return;
    setCapabilityBusy(true);
    setCapabilityError(null);
    try {
      await api.disableCapability(token, capabilityId);
      await refreshWorkspace(token, false);
    } catch (error) {
      setCapabilityError(error instanceof ApiError ? error.message : "Falha ao desabilitar capability.");
    } finally {
      setCapabilityBusy(false);
    }
  }

  async function handleExecuteAutomation() {
    if (!token) return;
    setCapabilityBusy(true);
    setCapabilityError(null);
    setAutomationResult(null);
    try {
      const result = await api.executeAutomation(token, {
        connector_id: "restricted_rest",
        capability: "http_request",
        payload: {
          method: "GET",
          url: "https://example.com",
          headers: {
            accept: "text/html",
            "user-agent": "the-creation-os-creator-interface",
          },
        },
        timeout_seconds: 10,
        idempotency_key: `creator-interface-${Date.now()}`,
      });
      setAutomationResult(result);
      await refreshWorkspace(token, false);
    } catch (error) {
      setCapabilityError(error instanceof ApiError ? error.message : "Automation negada pelo backend.");
    } finally {
      setCapabilityBusy(false);
    }
  }

  async function handleSend(event: FormEvent) {
    event.preventDefault();
    if (!token || !message.trim()) return;
    const text = message.trim();
    setMessage("");
    setBusy(true);
    setChat((items) => [...items, { id: crypto.randomUUID(), role: "creator", text, meta: "Creator" }]);
    try {
      const current = await ensureConversation(token);
      const god = await api.sendGod(token, current.id, text);
      setChat((items) => [
        ...items,
        {
          id: god.id,
          role: "god",
          text: god.reply.message,
          meta: `${god.interaction_type} / ${god.next_action}`,
        },
      ]);
      if (god.interaction_type === "POTENTIAL") {
        const trinity = await api.orchestrateTrinity(token, god.id);
        setChat((items) => [
          ...items,
          {
            id: trinity.rockmam_assessment_id,
            role: "trinity",
            text: `Trindade integrada: ROCKMAM retornou ${trinity.assessment_result}.`,
            meta: trinity.god_consolidated_result.creator_approval_required
              ? "Requires Creator approval"
              : "No approval request emitted",
          },
        ]);
      }
      await refreshWorkspace(token, false);
    } catch (error) {
      setChat((items) => [
        ...items,
        {
          id: crypto.randomUUID(),
          role: "god",
          text: error instanceof ApiError ? error.message : "The channel failed without changing backend state.",
          meta: "error",
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="creator-interface-exact" data-load-state={loadState} data-missions={missions.length}>
      <LivingUniverse
        agents={activeAgents}
        universes={universes}
        missions={missions}
        inceptions={visibleInceptions}
        chronicles={chronicles}
        manifestations={manifestations}
        pulse={pulse}
      />
      <PulseHeader pulse={pulse} authenticated={authenticated} />
      <InceptionPanel inceptions={visibleInceptions} />
      {dataError ? <div className="api-state api-state-error">{dataError}</div> : null}
      {empty ? <div className="api-state api-state-empty">API conectada sem dados ativos.</div> : null}
      {authenticated ? (
        <CapabilityPanel
          capabilities={capabilities}
          loading={capabilityBusy}
          error={capabilityError}
          result={automationResult}
          onEnable={handleEnableCapability}
          onDisable={handleDisableCapability}
          onExecute={handleExecuteAutomation}
        />
      ) : null}
      <GodChat
        authenticated={authenticated}
        busy={busy}
        message={message}
        password={password}
        onMessage={setMessage}
        onPassword={setPassword}
        onSend={handleSend}
        onLogin={handleLogin}
      />
      <ChronicleRibbon entries={chronicles} />
    </main>
  );
}
