import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { inferRequestedPanel, panelTitle, pendingInception, shouldClosePanel, normalizeEntityKey, type RequestedPanel } from "./appLogic";
import { CapabilityPanel } from "./components/CapabilityPanel";
import { ChronicleRibbon } from "./components/ChronicleRibbon";
import { InceptionPanel } from "./components/InceptionPanel";
import { EntityActivityState, HotspotSummary, LivingDashboard } from "./components/LivingDashboard";
import { MissionAuthorizationPanel } from "./components/MissionAuthorizationPanel";
import { OpportunityPanel } from "./components/OpportunityPanel";
import { PerceptionPanel } from "./components/PerceptionPanel";
import "./styles/living-dashboard.css";
import { buildContextualVoiceMessage, createBrowserSpeechRecognizer, stopAudioPlayback, type VoiceConversationState } from "./voice";
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
  Opportunity,
  PerceptionSource,
  Pulse,
  Universe,
} from "./types";

type LoadState = "idle" | "loading" | "ready" | "empty" | "error";

const REFRESH_INTERVAL_MS = 15000;
const WORKSPACE_CACHE_KEY = "creator-interface-workspace-cache";
const CREATOR_DEFAULT_USERNAME = import.meta.env.VITE_CREATOR_DEFAULT_USERNAME ?? "creator";
const CREATOR_DEV_PASSWORD = import.meta.env.VITE_CREATOR_DEV_PASSWORD ?? "";

type WorkspaceCache = {
  inceptions: Inception[];
  missions: Mission[];
  agents: Agent[];
  universes: Universe[];
  chronicles: ChronicleEntry[];
  capabilities: CapabilityFramework[];
  opportunities: Opportunity[];
  perceptionSources: PerceptionSource[];
  notifications: CreatorNotification[];
  missionAuthorization: MissionAuthorization | null;
  pulse: Pulse | null;
};

export function App() {
  const [token, setToken] = useState<string | null>(localStorage.getItem("creator-token"));
  const [username, setUsername] = useState(CREATOR_DEFAULT_USERNAME);
  const [password, setPassword] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [chat, setChat] = useState<ChatItem[]>([
    { id: "intro", role: "god", text: "DEUS esta presente. Aguardando a palavra do Criador.", meta: "local" },
  ]);
  const [message, setMessage] = useState("");
  const [inceptions, setInceptions] = useState<Inception[]>([]);
  const [inceptionBusy, setInceptionBusy] = useState(false);
  const [inceptionError, setInceptionError] = useState<string | null>(null);
  const [missions, setMissions] = useState<Mission[]>([]);
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
  const [authError, setAuthError] = useState<string | null>(null);
  const [requestedPanel, setRequestedPanel] = useState<RequestedPanel>(null);
  const [busy, setBusy] = useState(false);
  const [silentAuthAttempted, setSilentAuthAttempted] = useState(false);
  const [voiceState, setVoiceState] = useState<VoiceConversationState>("idle");
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef<string | null>(null);
  const voiceSubmittingRef = useRef(false);
  const submitVoiceRef = useRef<(text: string) => Promise<void>>(async () => undefined);

  const authenticated = Boolean(token);
  const empty = loadState === "empty";
  const activeMission = missions[0] ?? null;
  const lastGodReply = useMemo(() => [...chat].reverse().find((item) => item.role === "god")?.text ?? null, [chat]);
  const voiceContext = useMemo(
    () => ({
      currentSubject: chat.at(-1)?.text.slice(0, 120) ?? null,
      missionTitle: missions[0]?.title ?? null,
      opportunityTitle: opportunities[0]?.title ?? null,
      pendingDecision: inceptions.some(pendingInception) ? "inception_review" : opportunities[0] ? "opportunity_review" : null,
      lastGodReply,
    }),
    [chat, inceptions, lastGodReply, missions, opportunities],
  );
  const recognizer = useMemo(
    () =>
      createBrowserSpeechRecognizer({
        onStart: () => {
          setVoiceError(null);
          setVoiceState("listening");
        },
        onStop: () => {
          setVoiceState((current) => (current === "listening" ? "idle" : current));
        },
        onTranscript: (text) => {
          setMessage(text);
          void submitVoiceRef.current(text);
        },
        onError: (message) => {
          setVoiceError(message);
          setVoiceState("error");
        },
      }),
    [],
  );
  const universeSummaries = useMemo(
    () => buildHotspotSummaries({ agents, universes, opportunities, notifications, missions, inceptions, chronicles }),
    [agents, universes, opportunities, notifications, missions, inceptions, chronicles],
  );
  const activityStates = useMemo(
    () => buildActivityStates({ busy, voiceState, loadState, pulse, agents, opportunities, notifications, chat }),
    [busy, voiceState, loadState, pulse, agents, opportunities, notifications, chat],
  );

  useEffect(() => {
    if (!token) {
      // Resets local state when the workspace polling subscription below stops, not derived UI state.
      // eslint-disable-next-line react-hooks/set-state-in-effect
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

  useEffect(() => {
    if (token || silentAuthAttempted || !CREATOR_DEV_PASSWORD) return;
    // Guards the one-time silent-login network call below, not derived UI state.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSilentAuthAttempted(true);
    void api
      .login(CREATOR_DEFAULT_USERNAME, CREATOR_DEV_PASSWORD)
      .then((result) => {
        localStorage.setItem("creator-token", result.access_token);
        setToken(result.access_token);
        setAuthError(null);
      })
      .catch((error) => {
        setAuthError(error instanceof ApiError ? error.message : "Falha ao autenticar Criador.");
      });
  }, [silentAuthAttempted, token]);

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setRequestedPanel(null);
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, []);

  useEffect(() => {
    return () => stopVoiceAudio();
  }, []);

  function resetSession(message?: string) {
    localStorage.removeItem("creator-token");
    setToken(null);
    setConversation(null);
    setLoadState("idle");
    setDataError(null);
    if (message) setAuthError(message);
  }

  async function handleLogin(event: FormEvent) {
    event.preventDefault();
    if (!username.trim() || !password || authBusy) return;
    setAuthBusy(true);
    setAuthError(null);
    try {
      const result = await api.login(username.trim(), password);
      localStorage.setItem("creator-token", result.access_token);
      setToken(result.access_token);
      setPassword("");
    } catch (error) {
      setAuthError(error instanceof ApiError ? error.message : "Falha ao autenticar o Criador.");
    } finally {
      setAuthBusy(false);
    }
  }

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

    if (
      failures.some(
        (result) =>
          result.status === "rejected" &&
          result.reason instanceof ApiError &&
          result.reason.status === 401,
      )
    ) {
      resetSession("Sessao expirada ou invalida. Autentique o Criador novamente.");
      return;
    }

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

    const nextMissionAuthorization =
      nextMissions[0] ? await api.getMissionAuthorization(accessToken, nextMissions[0].id).catch(() => missionAuthorization) : null;

    setInceptions(nextInceptions);
    setMissions(nextMissions);
    setAgents(nextAgents);
    setUniverses(nextUniverses);
    setChronicles(nextChronicles);
    setPulse(nextPulse);
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
        loadedNotifications.value.length > 0);
    cacheWorkspace({
      inceptions: nextInceptions,
      missions: nextMissions,
      agents: nextAgents,
      universes: nextUniverses,
      chronicles: nextChronicles,
      missionAuthorization: nextMissionAuthorization,
      capabilities: nextCapabilities,
      opportunities: nextOpportunities,
      perceptionSources: nextPerceptionSources,
      notifications: nextNotifications,
      pulse: nextPulse,
    });
    setLoadState(hasData ? "ready" : "empty");
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

  async function handleSubmitInception(inceptionId: string) {
    if (!token) return;
    setInceptionBusy(true);
    setInceptionError(null);
    try {
      await api.submitInception(token, inceptionId);
      await refreshWorkspace(token, false);
    } catch (error) {
      setInceptionError(error instanceof ApiError ? error.message : "Falha ao enviar Inception.");
    } finally {
      setInceptionBusy(false);
    }
  }

  async function handleApproveInception(inceptionId: string) {
    if (!token) return;
    setInceptionBusy(true);
    setInceptionError(null);
    try {
      await api.approveInception(token, inceptionId);
      await refreshWorkspace(token, false);
    } catch (error) {
      setInceptionError(error instanceof ApiError ? error.message : "Falha ao aprovar Inception.");
    } finally {
      setInceptionBusy(false);
    }
  }

  async function handleRejectInception(inceptionId: string) {
    if (!token) return;
    setInceptionBusy(true);
    setInceptionError(null);
    try {
      await api.rejectInception(token, inceptionId);
      await refreshWorkspace(token, false);
    } catch (error) {
      setInceptionError(error instanceof ApiError ? error.message : "Falha ao negar Inception.");
    } finally {
      setInceptionBusy(false);
    }
  }

  async function handleCreateMissionFromInception(inception: Inception) {
    if (!token) return;
    setInceptionBusy(true);
    setInceptionError(null);
    try {
      await api.createMissionFromInception(token, inception);
      await refreshWorkspace(token, false);
    } catch (error) {
      setInceptionError(error instanceof ApiError ? error.message : "Falha ao criar missao.");
    } finally {
      setInceptionBusy(false);
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
    if (shouldClosePanel(normalized)) setRequestedPanel(null);
    const panelIntent = inferRequestedPanel(normalized);
    if (panelIntent) setRequestedPanel(panelIntent);
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
      if (error instanceof ApiError && error.status === 401) {
        resetSession("Sessao expirada ou invalida. Autentique o Criador novamente.");
      }
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

  useEffect(() => {
    submitVoiceRef.current = submitVoice;
  });

  async function submitVoice(text: string) {
    if (!token || busy || voiceSubmittingRef.current) return;
    voiceSubmittingRef.current = true;
    setMessage(text);
    const contextual = buildContextualVoiceMessage(text, voiceContext);
    setVoiceState("processing");
    setVoiceError(null);
    try {
      const reply = await sendToGod(contextual);
      await speakGodReply(reply);
    } catch (error) {
      setVoiceError(error instanceof Error ? error.message : "Falha na conversa por voz.");
      setVoiceState("error");
    } finally {
      voiceSubmittingRef.current = false;
      setMessage(text);
    }
  }

  async function speakGodReply(text: string) {
    if (!token || !text.trim()) {
      setVoiceState("idle");
      return;
    }
    try {
      setVoiceState("responding");
      const audio = await api.synthesizeVoice(token, text);
      stopVoiceAudio();
      const url = URL.createObjectURL(audio);
      audioUrlRef.current = url;
      const player = new Audio(url);
      audioRef.current = player;
      player.onended = () => {
        stopVoiceAudio();
        setVoiceState("idle");
      };
      player.onerror = () => {
        stopVoiceAudio();
        setVoiceError("Audio indisponivel. Resposta de DEUS mantida em texto.");
        setVoiceState("idle");
      };
      setVoiceState("speaking");
      await player.play();
    } catch (error) {
      setVoiceError(error instanceof ApiError ? "Audio indisponivel. Resposta de DEUS mantida em texto." : "Voz indisponivel.");
      setVoiceState("idle");
    }
  }

  function stopVoiceAudio() {
    stopAudioPlayback(audioRef.current, audioUrlRef.current);
    audioRef.current = null;
    audioUrlRef.current = null;
  }

  async function handleVoiceListen() {
    if (!recognizer.supported || voiceState === "listening" || voiceState === "processing" || voiceState === "responding") return;
    try {
      setVoiceError(null);
      await recognizer.start();
    } catch (error) {
      setVoiceError(error instanceof Error ? error.message : "Nao foi possivel iniciar o microfone.");
      setVoiceState("error");
    }
  }

  function handleVoiceStopListening() {
    recognizer.stop();
    setVoiceState("idle");
  }

  function handleVoiceStopSpeaking() {
    stopVoiceAudio();
    setVoiceState("idle");
  }

  async function handleSend(event: FormEvent) {
    event.preventDefault();
    if (!token || !message.trim()) return;
    const text = message.trim();
    setMessage("");
    await sendToGod(text).catch(() => undefined);
  }

  const demandPanel =
    authenticated && requestedPanel ? (
        <section className="deus-demand-panel" role="dialog" aria-modal="false" aria-label="Painel solicitado por DEUS">
          <header>
            <strong>{panelTitle(requestedPanel)}</strong>
            <button type="button" onClick={() => setRequestedPanel(null)}>
              Fechar
            </button>
          </header>
          <div className="creator-secondary-grid">
            {requestedPanel === "inceptions" ? (
              <InceptionPanel
                inceptions={inceptions}
                loading={inceptionBusy}
                error={inceptionError}
                onSubmit={handleSubmitInception}
                onApprove={handleApproveInception}
                onReject={handleRejectInception}
                onCreateMission={handleCreateMissionFromInception}
              />
            ) : null}
            {requestedPanel === "missions" ? (
              <MissionAuthorizationPanel
                mission={activeMission}
                authorization={missionAuthorization}
                loading={missionAuthorizationBusy}
                error={missionAuthorizationError}
                onRequest={handleRequestMissionAuthorization}
                onApprove={handleApproveMissionAuthorization}
                onRevoke={handleRevokeMissionAuthorization}
              />
            ) : null}
            {requestedPanel === "opportunities" ? (
              <OpportunityPanel
                opportunities={opportunities}
                loading={opportunityBusy}
                error={opportunityError}
                onDiscover={handleRunDiscovery}
                onApprove={handleApproveOpportunity}
                onReject={handleRejectOpportunity}
                onConvert={handleConvertOpportunity}
              />
            ) : null}
            {requestedPanel === "perception" ? (
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
            ) : null}
            {requestedPanel === "capabilities" ? (
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
            {requestedPanel === "chronicle" ? <ChronicleRibbon entries={chronicles} /> : null}
            {requestedPanel === "universes" ? (
              <section className="conversation-data-list" aria-label="Universos e agentes">
                <header>
                  <span>Universos</span>
                  <strong>{universes.length}</strong>
                </header>
                {universes.length === 0 ? <p>Nenhum universo retornado pela API.</p> : null}
                {universes.map((universe) => (
                  <article key={universe.id}>
                    <strong>{universe.name}</strong>
                    <span>
                      {universe.code} / {universe.active ? "ativo" : "inativo"}
                    </span>
                  </article>
                ))}
                <header>
                  <span>Agentes</span>
                  <strong>{agents.length}</strong>
                </header>
                {agents.length === 0 ? <p>Nenhum agente retornado pela API.</p> : null}
                {agents.map((agent) => (
                  <article key={agent.id}>
                    <strong>{agent.name}</strong>
                    <span>
                      {agent.universe} / {agent.status} / {agent.description}
                    </span>
                  </article>
                ))}
              </section>
            ) : null}
          </div>
        </section>
      ) : null;

  return (
    <>
      <LivingDashboard
        authenticated={authenticated}
        busy={busy}
        authBusy={authBusy}
        authError={authError}
        username={username}
        password={password}
        message={message}
        chat={chat}
        pulse={pulse}
        loadState={loadState}
        notifications={notifications}
        agents={agents}
        universes={universes}
        chronicles={chronicles}
        activityStates={activityStates}
        hotspotSummaries={universeSummaries}
        demandPanel={demandPanel}
        onSelectPanel={setRequestedPanel}
        voiceState={voiceState}
        voiceSupported={recognizer.supported}
        voiceError={voiceError}
        onUsername={setUsername}
        onPassword={setPassword}
        onLogin={handleLogin}
        onMessage={setMessage}
        onSend={handleSend}
        onVoiceListen={handleVoiceListen}
        onVoiceStopListening={handleVoiceStopListening}
        onVoiceStopSpeaking={handleVoiceStopSpeaking}
        onReadNotification={handleReadNotification}
      />
      {dataError ? <div className="api-state api-state-error">{dataError}</div> : null}
      {empty ? <div className="api-state api-state-empty">API conectada sem dados ativos.</div> : null}
    </>
  );
}

function buildActivityStates({
  busy,
  voiceState,
  loadState,
  pulse,
  agents,
  opportunities,
  notifications,
  chat,
}: {
  busy: boolean;
  voiceState: VoiceConversationState;
  loadState: LoadState;
  pulse: Pulse | null;
  agents: Agent[];
  opportunities: Opportunity[];
  notifications: CreatorNotification[];
  chat: ChatItem[];
}): Record<string, EntityActivityState> {
  const offline = loadState === "error" || pulse?.status === "unhealthy";
  const recentTrinity = [...chat].reverse().find((item) => item.role === "trinity");
  const unreadNotifications = notifications.some((notification) => notification.status === "unread");
  const activeByUniverse = new Set(
    agents
      .filter((agent) => agent.enabled && !["idle", "offline", "disabled"].includes(agent.status.toLowerCase()))
      .map((agent) => normalizeEntityKey(agent.universe)),
  );
  const opportunityByUniverse = new Set(opportunities.map((opportunity) => normalizeEntityKey(opportunity.universe)));

  const state: Record<string, EntityActivityState> = {
    deus: offline ? "offline" : busy || voiceState === "processing" ? "processing" : voiceState === "listening" || voiceState === "speaking" ? "active" : unreadNotifications ? "active" : "idle",
    sophia: busy ? "processing" : recentTrinity ? "completed" : "idle",
    rockmam: recentTrinity ? "completed" : opportunities.some((item) => item.status === "approved") ? "active" : "idle",
  };

  const universeIds = ["eng", "jur", "fin", "seg", "neg", "cie", "con", "cri"];
  for (const id of universeIds) {
    if (offline) state[id] = "offline";
    else if (activeByUniverse.has(id)) state[id] = "active";
    else if (opportunityByUniverse.has(id)) state[id] = "warning";
    else state[id] = "idle";
  }
  return state;
}

function buildHotspotSummaries({
  agents,
  universes,
  opportunities,
  notifications,
  missions,
  inceptions,
  chronicles,
}: {
  agents: Agent[];
  universes: Universe[];
  opportunities: Opportunity[];
  notifications: CreatorNotification[];
  missions: Mission[];
  inceptions: Inception[];
  chronicles: ChronicleEntry[];
}): Record<string, HotspotSummary> {
  const pendingInceptions = inceptions.filter(pendingInception);
  const pendingOpportunities = opportunities.filter((item) => item.status === "pending_creator_review");
  const unreadNotifications = notifications.filter((item) => item.status === "unread");
  const latestChronicle = chronicles[0];
  const base: Record<string, HotspotSummary> = {
    deus: {
      id: "deus",
      title: "DEUS",
      subtitle: "Presenca central",
      lines: [
        missions[0] ? `Missao ativa: ${missions[0].title}` : "Nenhuma missao ativa retornada pela API.",
        pendingInceptions.length > 0 ? `${pendingInceptions.length} Inception pendente.` : "Sem Inception pendente.",
        unreadNotifications.length > 0 ? `${unreadNotifications.length} notificacao real nao lida.` : "Sem notificacao real nao lida.",
      ],
    },
    sophia: {
      id: "sophia",
      title: "SOPHIA",
      subtitle: "Compreensao",
      lines: [
        latestChronicle ? `Ultimo evento: ${latestChronicle.event_type}` : "Nenhum discernimento recente retornado pela API.",
        "SOPHIA permanece somente na camada de compreensao.",
      ],
      actionLabel: "Ver Chronicle",
      panel: "chronicle",
    },
    rockmam: {
      id: "rockmam",
      title: "ROCKMAM",
      subtitle: "Possibilidade",
      lines: [
        pendingOpportunities[0] ? `Oportunidade: ${pendingOpportunities[0].title}` : "Nenhuma possibilidade pendente retornada pela API.",
        "ROCKMAM nao executa, apenas avalia possibilidade.",
      ],
      actionLabel: "Ver oportunidades",
      panel: "opportunities",
    },
  };

  const universeMap: Record<string, { label: string; query: string[]; panel?: HotspotSummary["panel"] }> = {
    eng: { label: "ENGENHARIA", query: ["eng", "engenharia", "engineering"], panel: "universes" },
    jur: { label: "JURIDICO", query: ["jur", "juridico", "legal"], panel: "universes" },
    fin: { label: "FINANCAS", query: ["fin", "finance", "financial", "financas"], panel: "opportunities" },
    seg: { label: "SEGURANCA", query: ["seg", "seguranca", "security"], panel: "universes" },
    neg: { label: "NEGOCIOS", query: ["neg", "negocios", "business"], panel: "opportunities" },
    cie: { label: "CIENCIA", query: ["cie", "ciencia", "science"], panel: "universes" },
    con: { label: "CONHECIMENTO", query: ["con", "conhecimento", "knowledge"], panel: "universes" },
    cri: { label: "CRIACAO", query: ["cri", "criacao", "creation"], panel: "universes" },
  };

  for (const [id, config] of Object.entries(universeMap)) {
    const relatedAgents = agents.filter((agent) => config.query.includes(normalizeEntityKey(agent.universe)));
    const activeAgents = relatedAgents.filter((agent) => agent.enabled && !["idle", "offline", "disabled"].includes(agent.status.toLowerCase()));
    const relatedUniverse = universes.find((universe) => config.query.includes(normalizeEntityKey(universe.code)) || config.query.includes(normalizeEntityKey(universe.name)));
    const relatedOpportunities = opportunities.filter((opportunity) => config.query.includes(normalizeEntityKey(opportunity.universe)));
    base[id] = {
      id,
      title: config.label,
      subtitle: relatedUniverse?.active ? "Universo ativo" : "Universo",
      lines: [
        `${relatedAgents.length} agentes retornados pela API.`,
        `${activeAgents.length} agentes ativos.`,
        relatedOpportunities[0] ? `Oportunidade: ${relatedOpportunities[0].title}` : "Nenhuma oportunidade relacionada no ranking atual.",
      ],
      actionLabel: "Ver detalhes",
      panel: config.panel,
    };
  }

  return base;
}
