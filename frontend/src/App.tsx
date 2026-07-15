import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "./api";
import { ChronicleRibbon } from "./components/ChronicleRibbon";
import { CosmicSystem } from "./components/CosmicSystem";
import { GodDock } from "./components/GodDock";
import { Needles } from "./components/Needles";
import { PulseHeader } from "./components/PulseHeader";
import type { Agent, ChatItem, ChronicleEntry, Conversation, Inception, Mission, Pulse, Universe } from "./types";

type LoadState = "idle" | "loading" | "ready" | "empty" | "error";

const REFRESH_INTERVAL_MS = 15000;

function normalizeStatus(value: string) {
  return value.toLowerCase();
}

function pendingInception(item: Inception) {
  return !["approved", "rejected", "cancelled"].includes(normalizeStatus(item.status));
}

export function App() {
  const [username, setUsername] = useState("creator");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState<string | null>(localStorage.getItem("creator-token"));
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [chat, setChat] = useState<ChatItem[]>([
    { id: "intro", role: "god", text: "GOD esta presente. Aguardando a palavra do Criador.", meta: "local" },
  ]);
  const [message, setMessage] = useState("");
  const [inceptions, setInceptions] = useState<Inception[]>([]);
  const [missions, setMissions] = useState<Mission[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [universes, setUniverses] = useState<Universe[]>([]);
  const [chronicles, setChronicles] = useState<ChronicleEntry[]>([]);
  const [pulse, setPulse] = useState<Pulse | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [dataError, setDataError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const authenticated = Boolean(token);
  const activeAgents = useMemo(() => agents.filter((agent) => agent.enabled), [agents]);
  const pendingInceptions = inceptions.filter(pendingInception);

  useEffect(() => {
    if (!token) {
      setLoadState("idle");
      return undefined;
    }
    void refreshWorkspace(token, true);
    const interval = window.setInterval(() => {
      void refreshWorkspace(token, false);
    }, REFRESH_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [token]);

  async function refreshWorkspace(accessToken: string, showLoading: boolean) {
    if (showLoading) setLoadState("loading");
    setDataError(null);
    const [loadedInceptions, loadedMissions, loadedAgents, loadedUniverses, loadedChronicles, loadedPulse] =
      await Promise.allSettled([
        api.listInceptions(accessToken),
        api.listMissions(accessToken),
        api.listAgents(accessToken),
        api.listUniverses(accessToken),
        api.listChronicles(accessToken),
        api.pulse(accessToken),
      ]);

    const failures = [loadedInceptions, loadedMissions, loadedAgents, loadedUniverses, loadedChronicles, loadedPulse].filter(
      (result) => result.status === "rejected",
    );

    if (loadedInceptions.status === "fulfilled") setInceptions(loadedInceptions.value);
    if (loadedMissions.status === "fulfilled") setMissions(loadedMissions.value);
    if (loadedAgents.status === "fulfilled") setAgents(loadedAgents.value);
    if (loadedUniverses.status === "fulfilled") setUniverses(loadedUniverses.value);
    if (loadedChronicles.status === "fulfilled") setChronicles(loadedChronicles.value);
    if (loadedPulse.status === "fulfilled") setPulse(loadedPulse.value);

    if (failures.length > 0) {
      setLoadState("error");
      setDataError("Some real backend data could not be loaded.");
      return;
    }

    const hasData =
      loadedInceptions.status === "fulfilled" &&
      loadedMissions.status === "fulfilled" &&
      loadedAgents.status === "fulfilled" &&
      loadedUniverses.status === "fulfilled" &&
      loadedChronicles.status === "fulfilled" &&
      (loadedInceptions.value.length > 0 ||
        loadedMissions.value.length > 0 ||
        loadedAgents.value.length > 0 ||
        loadedUniverses.value.length > 0 ||
        loadedChronicles.value.length > 0);
    setLoadState(hasData ? "ready" : "empty");
  }

  async function handleLogin(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setNotice(null);
    try {
      const result = await api.login(username, password);
      localStorage.setItem("creator-token", result.access_token);
      setToken(result.access_token);
      setNotice("Creator authenticated");
    } catch (error) {
      setNotice(error instanceof ApiError ? error.message : "Authentication failed");
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

  function logout() {
    localStorage.removeItem("creator-token");
    setToken(null);
    setConversation(null);
    setInceptions([]);
    setMissions([]);
    setAgents([]);
    setUniverses([]);
    setChronicles([]);
    setPulse(null);
  }

  return (
    <main className="creation-universe">
      <PulseHeader
        pulse={pulse}
        loadState={loadState}
        authenticated={authenticated}
        activeAgents={activeAgents.length}
        refreshSeconds={REFRESH_INTERVAL_MS / 1000}
      />
      <CosmicSystem agents={activeAgents} universes={universes} loadState={loadState} />
      <Needles inceptions={pendingInceptions} missions={missions} loadState={loadState} dataError={dataError} />
      <GodDock
        authenticated={authenticated}
        busy={busy}
        username={username}
        password={password}
        message={message}
        chat={chat}
        notice={notice}
        onUsername={setUsername}
        onPassword={setPassword}
        onMessage={setMessage}
        onLogin={handleLogin}
        onSend={handleSend}
        onLogout={logout}
      />
      <ChronicleRibbon entries={chronicles} loading={loadState === "loading"} />
    </main>
  );
}
