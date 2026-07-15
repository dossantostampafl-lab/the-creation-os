import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  Activity,
  Bot,
  Fingerprint,
  Lock,
  Milestone,
  Orbit,
  Send,
  Shield,
  Sparkles,
  User,
} from "lucide-react";
import { api, ApiError } from "./api";
import type { Agent, ChatItem, ChronicleEntry, Conversation, Inception, Mission, Pulse, Universe } from "./types";

type LoadState = "idle" | "loading" | "ready" | "empty" | "error";

const REFRESH_INTERVAL_MS = 15000;

function normalizeStatus(value: string) {
  return value.toLowerCase();
}

function pendingInception(item: Inception) {
  return !["approved", "rejected", "cancelled"].includes(normalizeStatus(item.status));
}

function positionFor(index: number, total: number) {
  const safeTotal = Math.max(total, 1);
  const angle = (index / safeTotal) * Math.PI * 2 - Math.PI / 2;
  const radiusX = 31 + (index % 2) * 7;
  const radiusY = 24 + (index % 3) * 5;
  return {
    x: 50 + Math.cos(angle) * radiusX,
    y: 50 + Math.sin(angle) * radiusY,
  };
}

function universeLabel(agent: Agent) {
  return agent.universe || "unassigned";
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
  const visibleUniverses = useMemo(() => {
    if (universes.length > 0) return universes;
    const names = Array.from(new Set(agents.map((agent) => universeLabel(agent)))).filter(Boolean);
    return names.map((name) => ({
      id: `derived-${name}`,
      code: name,
      name,
      active: true,
      created_at: "",
    }));
  }, [agents, universes]);

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
    <main className="shell">
      <aside className="side-nav">
        <div className="brand">
          <Orbit size={24} />
          <span>THE CREATION OS</span>
        </div>
        <nav>
          <a className="active"><Bot size={18} />GOD</a>
          <a><Sparkles size={18} />Trinity</a>
          <a><Milestone size={18} />Missions</a>
          <a><Activity size={18} />Pulse</a>
          <a><Fingerprint size={18} />Chronicle</a>
        </nav>
        <div className="auth-box">
          {authenticated ? (
            <>
              <span><Shield size={16} /> Creator session active</span>
              <button type="button" onClick={logout}>Lock</button>
            </>
          ) : (
            <form onSubmit={handleLogin}>
              <label>
                <User size={14} />
                <input value={username} onChange={(event) => setUsername(event.target.value)} placeholder="creator" />
              </label>
              <label>
                <Lock size={14} />
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="password"
                />
              </label>
              <button disabled={busy} type="submit">Enter</button>
            </form>
          )}
          {notice && <small>{notice}</small>}
        </div>
      </aside>

      <section className="main-stage">
        <header className="pulse-bar">
          <div>
            <span className={`pulse-dot ${pulse?.status === "degraded" || loadState === "error" ? "degraded" : ""}`} />
            Pulse: {pulse?.status ?? (authenticated ? loadState : "locked")}
          </div>
          <div>Agents: {pulse?.active_agents ?? activeAgents.length}</div>
          <div>Chronicle: {pulse?.chronicles_chain.valid === false ? "invalid" : "verified"}</div>
          <div>Refresh: {REFRESH_INTERVAL_MS / 1000}s</div>
        </header>

        {dataError && <div className="data-banner">{dataError}</div>}

        <section className="stage-grid">
          <section className="god-chat">
            <div className="section-title">
              <Bot size={18} />
              <span>Direct Channel to GOD</span>
            </div>
            <div className="messages">
              {chat.map((item) => (
                <article key={item.id} className={`message ${item.role}`}>
                  <p>{item.text}</p>
                  {item.meta && <span>{item.meta}</span>}
                </article>
              ))}
            </div>
            <form className="composer" onSubmit={handleSend}>
              <input
                disabled={!authenticated || busy}
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                placeholder={authenticated ? "Speak to GOD" : "Authenticate Creator first"}
              />
              <button disabled={!authenticated || busy || !message.trim()} type="submit" aria-label="Send to GOD">
                <Send size={18} />
              </button>
            </form>
          </section>

          <section className="universe-map">
            <div className="milky-way" />
            {loadState === "loading" && <p className="map-state">Loading real universes and agents...</p>}
            {loadState !== "loading" && visibleUniverses.length === 0 && (
              <p className="map-state">No Universes or Agents returned by the backend.</p>
            )}
            {visibleUniverses.map((universe, index) => {
              const position = positionFor(index, visibleUniverses.length);
              return (
                <div key={universe.id} className="constellation" style={{ left: `${position.x}%`, top: `${position.y}%` }}>
                  <span />
                  <strong>{universe.name}</strong>
                </div>
              );
            })}
            {activeAgents.map((agent, index) => {
              const universeIndex = Math.max(
                visibleUniverses.findIndex((universe) => universe.code === agent.universe || universe.name === agent.universe),
                0,
              );
              const base = positionFor(universeIndex + index / Math.max(activeAgents.length, 1), Math.max(visibleUniverses.length, 1));
              return (
                <div
                  key={agent.id}
                  className="agent-star"
                  style={{
                    left: `${base.x + ((index % 3) - 1) * 6}%`,
                    top: `${base.y + ((index % 2) - 0.5) * 8}%`,
                  }}
                  title={`${agent.name} / ${universeLabel(agent)} / ${agent.status}`}
                >
                  <i />
                  <span>{agent.name}</span>
                </div>
              );
            })}
          </section>

          <aside className="right-column">
            <section className="compact-panel">
              <div className="section-title">Pending Inceptions</div>
              {loadState === "loading" ? <p className="quiet">Loading Inceptions...</p> : null}
              {loadState !== "loading" && pendingInceptions.length === 0 ? (
                <p className="quiet">No pending Inceptions returned by the backend.</p>
              ) : (
                pendingInceptions.slice(0, 4).map((item) => (
                  <article key={item.id} className="list-item">
                    <strong>{item.title}</strong>
                    <span>{item.status}</span>
                  </article>
                ))
              )}
            </section>
            <section className="compact-panel">
              <div className="section-title">Missions</div>
              {loadState === "loading" ? <p className="quiet">Loading Missions...</p> : null}
              {loadState !== "loading" && missions.length === 0 ? (
                <p className="quiet">No Missions returned by the backend.</p>
              ) : (
                missions.slice(0, 4).map((item) => (
                  <article key={item.id} className="list-item">
                    <strong>{item.title}</strong>
                    <span>{item.status}</span>
                  </article>
                ))
              )}
            </section>
          </aside>
        </section>

        <footer className="chronicle-strip">
          {loadState === "loading" ? <span>Loading Chronicle...</span> : null}
          {loadState !== "loading" && chronicles.length === 0 ? <span>No Chronicle entries returned by the backend.</span> : null}
          {chronicles.map((entry) => (
            <span key={entry.id}>
              <strong>#{entry.position} {entry.actor_role}</strong> {entry.event_type} / {entry.aggregate_type}
            </span>
          ))}
        </footer>
      </section>
    </main>
  );
}
