import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "./api";
import { CapabilityPanel } from "./components/CapabilityPanel";
import { ChronicleRibbon } from "./components/ChronicleRibbon";
import { GodChat } from "./components/GodChat";
import { InceptionPanel } from "./components/InceptionPanel";
import { LivingUniverse } from "./components/LivingUniverse";
import { MissionAuthorizationPanel } from "./components/MissionAuthorizationPanel";
import { OpportunityPanel } from "./components/OpportunityPanel";
import { PerceptionPanel } from "./components/PerceptionPanel";
import { PulseHeader } from "./components/PulseHeader";
import { VoiceConversation } from "./components/VoiceConversation";
import type {
  Agent,
  AutomationExecution,
  CapabilityFramework,
  ChatItem,
  ChronicleEntry,
  Conversation,
  CreatorNotification,
  Inception,
  Mission,
  MissionAuthorization,
  MissionManifestation,
  Opportunity,
  PerceptionSource,
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
  opportunities: Opportunity[];
  perceptionSources: PerceptionSource[];
  notifications: CreatorNotification[];
  missionAuthorization: MissionAuthorization | null;
  pulse: Pulse | null;
};

function normalizeStatus(value: string) {
  return value.toLowerCase();
}

function pendingInception(item: Inception) {
  return !["approved", "rejected", "cancelled"].includes(normalizeStatus(item.status));
}

function percent(value: number) {
  return `${Math.round(value * 100)}%`;
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
  const [missionAuthorization, setMissionAuthorization] = useState<MissionAuthorization | null>(null);
  const [missionAuthorizationBusy, setMissionAuthorizationBusy] = useState(false);
  const [missionAuthorizationError, setMissionAuthorizationError] = useState<string | null>(null);
  const [capabilities, setCapabilities] = useState<CapabilityFramework[]>([]);
  const [automationResult, setAutomationResult] = useState<AutomationExecution | null>(null);
  const [capabilityError, setCapabilityError] = useState<string | null>(null);
  const [capabilityBusy, setCapabilityBusy] = useState(false);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [opportunityBusy, setOpportunityBusy] = useState(false);
  const [opportunityError, setOpportunityError] = useState<string | null>(null);
  const [perceptionSources, setPerceptionSources] = useState<PerceptionSource[]>([]);
  const [notifications, setNotifications] = useState<CreatorNotification[]>([]);
  const [perceptionBusy, setPerceptionBusy] = useState(false);
  const [perceptionError, setPerceptionError] = useState<string | null>(null);
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
  const activeMission = missions[0] ?? null;
  const topOpportunities = useMemo(
    () => [...opportunities].sort((left, right) => right.priority_score - left.priority_score).slice(0, 3),
    [opportunities],
  );
  const pendingDecisions = useMemo(() => {
    const decisions: Array<{
      id: string;
      title: string;
      detail: string;
      action: string;
      disabled?: boolean;
      onClick?: () => void;
    }> = [];

    visibleInceptions.slice(0, 2).forEach((item) => {
      decisions.push({
        id: `inception-${item.id}`,
        title: item.title,
        detail: `Inception aguardando revisao do Criador (${item.status}).`,
        action: "Analisar",
      });
    });

    if (activeMission && (!missionAuthorization || missionAuthorization.status === "pending")) {
      decisions.push({
        id: `mission-auth-${activeMission.id}`,
        title: "Autorizacao da missao",
        detail: `${activeMission.title} exige autorizacao explicita do Criador.`,
        action: missionAuthorization?.status === "pending" ? "Aprovar" : "Analisar",
        disabled: missionAuthorizationBusy,
        onClick:
          missionAuthorization?.status === "pending"
            ? () => handleApproveMissionAuthorization(activeMission.id)
            : () => handleRequestMissionAuthorization(activeMission.id),
      });
    }

    if (activeMission && missionAuthorization?.status === "suspended") {
      decisions.push({
        id: `mission-suspended-${activeMission.id}`,
        title: "Missao suspensa",
        detail: "A missao esta suspensa e exige decisao do Criador.",
        action: "Analisar",
      });
    }

    opportunities
      .filter((item) => item.status === "pending_creator_review")
      .slice(0, 2)
      .forEach((item) => {
        decisions.push({
          id: `opportunity-${item.id}`,
          title: item.title,
          detail: `Oportunidade com score ${percent(item.priority_score)} aguardando aprovacao.`,
          action: "Aprovar",
          disabled: opportunityBusy,
          onClick: () => window.confirm("Aprovar esta oportunidade?") && handleApproveOpportunity(item.id),
        });
      });

    notifications
      .filter((item) => item.status === "unread")
      .slice(0, 2)
      .forEach((item) => {
        decisions.push({
          id: `notification-${item.id}`,
          title: item.title,
          detail: item.message,
          action: "Analisar",
          onClick: () => handleReadNotification(item.id),
        });
      });

    return decisions.slice(0, 5);
  }, [
    activeMission,
    missionAuthorization,
    missionAuthorizationBusy,
    notifications,
    opportunities,
    opportunityBusy,
    visibleInceptions,
  ]);

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
      setMissionAuthorization(workspace.missionAuthorization ?? null);
      setCapabilities(workspace.capabilities ?? []);
      setOpportunities(workspace.opportunities ?? []);
      setPerceptionSources(workspace.perceptionSources ?? []);
      setNotifications(workspace.notifications ?? []);
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
    const [
      loadedInceptions,
      loadedMissions,
      loadedAgents,
      loadedUniverses,
      loadedChronicles,
      loadedPulse,
      loadedCapabilities,
      loadedOpportunities,
      loadedPerceptionSources,
      loadedNotifications,
    ] =
      await Promise.allSettled([
        api.listInceptions(accessToken),
        api.listMissions(accessToken),
        api.listAgents(accessToken),
        api.listUniverses(accessToken),
        api.listChronicles(accessToken),
        api.pulse(accessToken),
        api.listCapabilities(accessToken),
        api.listOpportunities(accessToken),
        api.listPerceptionSources(accessToken),
        api.listNotifications(accessToken),
      ]);

    const failures = [
      loadedInceptions,
      loadedMissions,
      loadedAgents,
      loadedUniverses,
      loadedChronicles,
      loadedPulse,
      loadedCapabilities,
      loadedOpportunities,
      loadedPerceptionSources,
      loadedNotifications,
    ].filter((result) => result.status === "rejected");

    const nextInceptions = loadedInceptions.status === "fulfilled" ? loadedInceptions.value : inceptions;
    const nextMissions = loadedMissions.status === "fulfilled" ? loadedMissions.value : missions;
    const nextAgents = loadedAgents.status === "fulfilled" ? loadedAgents.value : agents;
    const nextUniverses = loadedUniverses.status === "fulfilled" ? loadedUniverses.value : universes;
    const nextChronicles = loadedChronicles.status === "fulfilled" ? loadedChronicles.value : chronicles;
    const nextPulse = loadedPulse.status === "fulfilled" ? loadedPulse.value : pulse;
    const nextCapabilities = loadedCapabilities.status === "fulfilled" ? loadedCapabilities.value : capabilities;
    const nextOpportunities = loadedOpportunities.status === "fulfilled" ? loadedOpportunities.value : opportunities;
    const nextPerceptionSources = loadedPerceptionSources.status === "fulfilled" ? loadedPerceptionSources.value : perceptionSources;
    const nextNotifications = loadedNotifications.status === "fulfilled" ? loadedNotifications.value : notifications;

    const manifestationResults = await Promise.allSettled(
      nextMissions.map((mission) => api.getMissionManifestation(accessToken, mission.id)),
    );
    const nextManifestations = manifestationResults.flatMap((result) => (result.status === "fulfilled" ? [result.value] : []));
    const nextMissionAuthorization =
      nextMissions[0] ? await api.getMissionAuthorization(accessToken, nextMissions[0].id).catch(() => missionAuthorization) : null;

    setInceptions(nextInceptions);
    setMissions(nextMissions);
    setAgents(nextAgents);
    setUniverses(nextUniverses);
    setChronicles(nextChronicles);
    setPulse(nextPulse);
    setManifestations(nextManifestations);
    setMissionAuthorization(nextMissionAuthorization);
    setCapabilities(nextCapabilities);
    setOpportunities(nextOpportunities);
    setPerceptionSources(nextPerceptionSources);
    setNotifications(nextNotifications);

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
      loadedOpportunities.status === "fulfilled" &&
      loadedPerceptionSources.status === "fulfilled" &&
      loadedNotifications.status === "fulfilled" &&
      (loadedInceptions.value.length > 0 ||
        loadedMissions.value.length > 0 ||
        loadedAgents.value.length > 0 ||
        loadedUniverses.value.length > 0 ||
        loadedChronicles.value.length > 0 ||
        loadedCapabilities.value.length > 0 ||
        loadedOpportunities.value.length > 0 ||
        loadedPerceptionSources.value.length > 0 ||
        loadedNotifications.value.length > 0 ||
        nextManifestations.length > 0);
    cacheWorkspace({
      inceptions: nextInceptions,
      missions: nextMissions,
      agents: nextAgents,
      universes: nextUniverses,
      chronicles: nextChronicles,
      manifestations: nextManifestations,
      missionAuthorization: nextMissionAuthorization,
      capabilities: nextCapabilities,
      opportunities: nextOpportunities,
      perceptionSources: nextPerceptionSources,
      notifications: nextNotifications,
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

  async function handleRunDiscovery() {
    if (!token) return;
    setOpportunityBusy(true);
    setOpportunityError(null);
    try {
      await api.runOpportunityDiscovery(token);
      await refreshWorkspace(token, false);
    } catch (error) {
      setOpportunityError(error instanceof ApiError ? error.message : "Falha ao executar descoberta.");
    } finally {
      setOpportunityBusy(false);
    }
  }

  async function handleApproveOpportunity(opportunityId: string) {
    if (!token) return;
    setOpportunityBusy(true);
    setOpportunityError(null);
    try {
      await api.approveOpportunity(token, opportunityId);
      await refreshWorkspace(token, false);
    } catch (error) {
      setOpportunityError(error instanceof ApiError ? error.message : "Falha ao aprovar oportunidade.");
    } finally {
      setOpportunityBusy(false);
    }
  }

  async function handleRejectOpportunity(opportunityId: string) {
    if (!token) return;
    setOpportunityBusy(true);
    setOpportunityError(null);
    try {
      await api.rejectOpportunity(token, opportunityId);
      await refreshWorkspace(token, false);
    } catch (error) {
      setOpportunityError(error instanceof ApiError ? error.message : "Falha ao rejeitar oportunidade.");
    } finally {
      setOpportunityBusy(false);
    }
  }

  async function handleConvertOpportunity(opportunityId: string) {
    if (!token) return;
    setOpportunityBusy(true);
    setOpportunityError(null);
    try {
      await api.convertOpportunity(token, opportunityId);
      await refreshWorkspace(token, false);
    } catch (error) {
      setOpportunityError(error instanceof ApiError ? error.message : "Falha ao converter oportunidade.");
    } finally {
      setOpportunityBusy(false);
    }
  }

  async function handleEnablePerceptionSource(sourceId: string) {
    if (!token) return;
    setPerceptionBusy(true);
    setPerceptionError(null);
    try {
      await api.enablePerceptionSource(token, sourceId);
      await refreshWorkspace(token, false);
    } catch (error) {
      setPerceptionError(error instanceof ApiError ? error.message : "Falha ao ativar fonte.");
    } finally {
      setPerceptionBusy(false);
    }
  }

  async function handleDisablePerceptionSource(sourceId: string) {
    if (!token) return;
    setPerceptionBusy(true);
    setPerceptionError(null);
    try {
      await api.disablePerceptionSource(token, sourceId);
      await refreshWorkspace(token, false);
    } catch (error) {
      setPerceptionError(error instanceof ApiError ? error.message : "Falha ao desativar fonte.");
    } finally {
      setPerceptionBusy(false);
    }
  }

  async function handleRunPerceptionSource(sourceId: string) {
    if (!token) return;
    setPerceptionBusy(true);
    setPerceptionError(null);
    try {
      await api.runPerceptionSource(token, sourceId);
      await refreshWorkspace(token, false);
    } catch (error) {
      setPerceptionError(error instanceof ApiError ? error.message : "Falha na coleta da fonte.");
    } finally {
      setPerceptionBusy(false);
    }
  }

  async function handleReadNotification(notificationId: string) {
    if (!token) return;
    try {
      await api.readNotification(token, notificationId);
      await refreshWorkspace(token, false);
    } catch (error) {
      setPerceptionError(error instanceof ApiError ? error.message : "Falha ao marcar notificacao.");
    }
  }

  async function handleRequestMissionAuthorization(missionId: string) {
    if (!token) return;
    setMissionAuthorizationBusy(true);
    setMissionAuthorizationError(null);
    try {
      await api.requestMissionAuthorization(token, missionId, "local");
      await refreshWorkspace(token, false);
    } catch (error) {
      setMissionAuthorizationError(error instanceof ApiError ? error.message : "Falha ao solicitar autorizacao.");
    } finally {
      setMissionAuthorizationBusy(false);
    }
  }

  async function handleApproveMissionAuthorization(missionId: string) {
    if (!token) return;
    setMissionAuthorizationBusy(true);
    setMissionAuthorizationError(null);
    try {
      await api.approveMissionAuthorization(token, missionId);
      await refreshWorkspace(token, false);
    } catch (error) {
      setMissionAuthorizationError(error instanceof ApiError ? error.message : "Falha ao autorizar missao.");
    } finally {
      setMissionAuthorizationBusy(false);
    }
  }

  async function handleRevokeMissionAuthorization(missionId: string) {
    if (!token) return;
    setMissionAuthorizationBusy(true);
    setMissionAuthorizationError(null);
    try {
      await api.revokeMissionAuthorization(token, missionId);
      await refreshWorkspace(token, false);
    } catch (error) {
      setMissionAuthorizationError(error instanceof ApiError ? error.message : "Falha ao revogar missao.");
    } finally {
      setMissionAuthorizationBusy(false);
    }
  }

  async function sendToGod(text: string) {
    if (!token || !text.trim()) return "";
    const normalized = text.trim();
    setBusy(true);
    setChat((items) => [...items, { id: crypto.randomUUID(), role: "creator", text: normalized, meta: "Creator" }]);
    try {
      const current = await ensureConversation(token);
      const god = await api.sendGod(token, current.id, normalized);
      setChat((items) => [
        ...items,
        {
          id: god.id,
          role: "god",
          text: god.reply.message,
          meta: `${god.interaction_type} / ${god.next_action}`,
        },
      ]);
      let spokenReply = god.reply.message;
      if (god.interaction_type === "POTENTIAL") {
        const trinity = await api.orchestrateTrinity(token, god.id);
        const trinityReply = `Trindade integrada: ROCKMAM retornou ${trinity.assessment_result}.`;
        spokenReply = `${spokenReply} ${trinityReply}`;
        setChat((items) => [
          ...items,
          {
            id: trinity.rockmam_assessment_id,
            role: "trinity",
            text: trinityReply,
            meta: trinity.god_consolidated_result.creator_approval_required
              ? "Requires Creator approval"
              : "No approval request emitted",
          },
        ]);
      }
      await refreshWorkspace(token, false);
      return spokenReply;
    } catch (error) {
      const text = error instanceof ApiError ? error.message : "The channel failed without changing backend state.";
      setChat((items) => [
        ...items,
        {
          id: crypto.randomUUID(),
          role: "god",
          text,
          meta: "error",
        },
      ]);
      throw error instanceof Error ? error : new Error(text);
    } finally {
      setBusy(false);
    }
  }

  async function handleSend(event: FormEvent) {
    event.preventDefault();
    if (!token || !message.trim()) return;
    const text = message.trim();
    setMessage("");
    await sendToGod(text).catch(() => undefined);
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
      {dataError ? <div className="api-state api-state-error">{dataError}</div> : null}
      {empty ? <div className="api-state api-state-empty">API conectada sem dados ativos.</div> : null}
      <section className="creator-home" aria-label="Creator Interface principal">
        <section className="creator-god-presence" aria-label="GOD e conversa">
          <div className="god-presence-header">
            <span>GOD</span>
            <strong>{authenticated ? "Presente" : "Aguardando autenticacao"}</strong>
            <em>{busy ? "processing" : "idle"}</em>
          </div>
          <p className="god-last-response">{chat.filter((item) => item.role === "god").at(-1)?.text ?? "GOD esta presente."}</p>
          <div className="god-context-strip">
            <span>{activeMission ? `Missao: ${activeMission.title}` : "Sem missao ativa"}</span>
            <span>{topOpportunities[0] ? `Oportunidade: ${topOpportunities[0].title}` : "Sem oportunidade prioritaria"}</span>
            <span>{pendingDecisions.length ? `${pendingDecisions.length} decisao pendente` : "Sem decisao pendente"}</span>
          </div>
          {authenticated ? (
            <VoiceConversation
              authenticated={authenticated}
              busy={busy}
              token={token}
              chat={chat}
              missions={missions}
              opportunities={opportunities}
              onSendToGod={sendToGod}
            />
          ) : (
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
          )}
        </section>

        <section className="creator-focus-grid" aria-label="Prioridades do Criador">
          <article className="creator-focus-card active-mission-card">
            <header>
              <span>Missao ativa</span>
              <strong>{activeMission?.status ?? "sem missao"}</strong>
            </header>
            {activeMission ? (
              <>
                <h2>{activeMission.title}</h2>
                <p>{activeMission.objective}</p>
                <div className="mission-progress">
                  <span style={{ width: missionAuthorization?.status === "authorized" ? "62%" : "18%" }} />
                </div>
                <dl>
                  <div>
                    <dt>Progresso</dt>
                    <dd>{missionAuthorization?.status === "authorized" ? "em execucao autorizada" : "aguardando autorizacao"}</dd>
                  </div>
                  <div>
                    <dt>Proxima acao</dt>
                    <dd>{missionAuthorization?.status === "authorized" ? "acompanhar resultado" : "decisao do Criador"}</dd>
                  </div>
                  <div>
                    <dt>Autorizacao</dt>
                    <dd>{missionAuthorization?.status ?? "nao solicitada"}</dd>
                  </div>
                </dl>
                <a href="#creator-secondary">Abrir detalhes</a>
              </>
            ) : (
              <p>Nenhuma missao ativa retornada pela API.</p>
            )}
          </article>

          <article className="creator-focus-card decisions-card">
            <header>
              <span>Decisoes pendentes</span>
              <strong>{pendingDecisions.length}</strong>
            </header>
            {pendingDecisions.length === 0 ? <p>Nenhuma acao direta do Criador neste momento.</p> : null}
            {pendingDecisions.map((item) => (
              <div className="decision-item" key={item.id}>
                <div>
                  <strong>{item.title}</strong>
                  <p>{item.detail}</p>
                </div>
                <button type="button" disabled={item.disabled} onClick={item.onClick}>
                  {item.action}
                </button>
              </div>
            ))}
          </article>

          <article className="creator-focus-card priority-opportunities-card">
            <header>
              <span>Oportunidades prioritarias</span>
              <button type="button" disabled={opportunityBusy} onClick={handleRunDiscovery}>
                Atualizar
              </button>
            </header>
            {topOpportunities.length === 0 ? <p>Nenhuma oportunidade relevante detectada.</p> : null}
            {topOpportunities.map((item) => (
              <div className="priority-opportunity" key={item.id}>
                <strong>{item.title}</strong>
                <span>
                  {item.universe} / score {percent(item.priority_score)}
                </span>
                <p>{item.summary}</p>
                <a href="#creator-secondary">Analisar</a>
              </div>
            ))}
            {opportunityError ? <p className="opportunity-error">{opportunityError}</p> : null}
          </article>
        </section>
      </section>

      {authenticated ? (
        <details className="creator-secondary" id="creator-secondary">
          <summary>Areas secundarias</summary>
          <div className="creator-secondary-grid">
            <InceptionPanel inceptions={visibleInceptions} />
            <MissionAuthorizationPanel
              mission={activeMission}
              authorization={missionAuthorization}
              loading={missionAuthorizationBusy}
              error={missionAuthorizationError}
              onRequest={handleRequestMissionAuthorization}
              onApprove={handleApproveMissionAuthorization}
              onRevoke={handleRevokeMissionAuthorization}
            />
            <OpportunityPanel
              opportunities={opportunities}
              loading={opportunityBusy}
              error={opportunityError}
              onDiscover={handleRunDiscovery}
              onApprove={handleApproveOpportunity}
              onReject={handleRejectOpportunity}
              onConvert={handleConvertOpportunity}
            />
            <PerceptionPanel
              sources={perceptionSources}
              notifications={notifications}
              loading={perceptionBusy}
              error={perceptionError}
              onEnable={handleEnablePerceptionSource}
              onDisable={handleDisablePerceptionSource}
              onRun={handleRunPerceptionSource}
              onReadNotification={handleReadNotification}
            />
            <CapabilityPanel
              capabilities={capabilities}
              loading={capabilityBusy}
              error={capabilityError}
              result={automationResult}
              onEnable={handleEnableCapability}
              onDisable={handleDisableCapability}
              onExecute={handleExecuteAutomation}
            />
          </div>
        </details>
      ) : null}
      <ChronicleRibbon entries={chronicles} />
    </main>
  );
}
