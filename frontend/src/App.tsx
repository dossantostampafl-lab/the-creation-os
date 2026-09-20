import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import type { InceptionView } from "./api";
import { DecisionsPanel } from "./DecisionsPanel";
import { fetchChronicleHistory, fetchInceptions, fetchInferenceStatus, fetchProjectionStatus, fetchSystemState, loginCreator, logoutCreator, streamChronicle } from "./api";
import { CreatorConsole } from "./CreatorConsole";
import type { ChronicleEvent, ChronicleRecord, InferenceStatusSnapshot, ProjectionStatus, SystemState } from "./types";

function statusTone(status: string): string {
  const value = status.toUpperCase();
  if (["MANIFESTED", "SUCCEEDED", "CURRENT", "ACTIVE", "HEALTHY", "AVAILABLE"].includes(value)) return "good";
  if (["FAILED", "BLOCKED", "INVALID", "DEGRADED", "UNAVAILABLE"].includes(value)) return "bad";
  if (["RUNNING", "EXECUTING", "DISTRIBUTED", "READY", "LAGGING", "UNCONFIGURED"].includes(value)) return "warn";
  return "neutral";
}

const formatStamp = (value: string) => new Date(value).toLocaleString([], { dateStyle: "short", timeStyle: "medium" });

function App() {
  const [state, setState] = useState<SystemState | null>(null);
  const [projections, setProjections] = useState<ProjectionStatus | null>(null);
  const [inference, setInference] = useState<InferenceStatusSnapshot | null>(null);
  const [chronicle, setChronicle] = useState<ChronicleRecord[]>([]);
  const [events, setEvents] = useState<ChronicleEvent[]>([]);
  const [connection, setConnection] = useState<"CONNECTING" | "LIVE" | "RESYNCING" | "AUTH_REQUIRED" | "ERROR">("CONNECTING");
  const [error, setError] = useState<string | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loginPending, setLoginPending] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [authVersion, setAuthVersion] = useState(0);
  const [retryVersion, setRetryVersion] = useState(0);
  const [inceptions, setInceptions] = useState<InceptionView[] | null>(null);
  const cursor = useRef(0);
  const refreshSeq = useRef(0);

  // Refetch live state; a stale response never overwrites a newer one. Inceptions load separately so they never block the dashboard.
  const refreshLive = useCallback(async () => {
    const seq = ++refreshSeq.current;
    void fetchInceptions()
      .then((next) => { if (seq === refreshSeq.current) setInceptions(next); })
      .catch(() => { if (seq === refreshSeq.current) setInceptions(null); });
    try {
      const [next, nextProjections, nextInference] = await Promise.all([fetchSystemState(), fetchProjectionStatus(), fetchInferenceStatus()]);
      if (seq !== refreshSeq.current) return;
      setState(next);
      setProjections(nextProjections);
      setInference(nextInference);
    } catch (refreshError) {
      if (seq === refreshSeq.current && refreshError instanceof Error && refreshError.message === "AUTH_REQUIRED") {
        setError(refreshError.message);
        setConnection("AUTH_REQUIRED");
      }
    }
  }, []);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    let refreshTimer: number | undefined;

    const fail = (failure: unknown, fallback: string) => {
      const message = failure instanceof Error ? failure.message : fallback;
      setError(message);
      setConnection(message === "AUTH_REQUIRED" ? "AUTH_REQUIRED" : "ERROR");
    };

    // Coalesce bursts of events into one refetch.
    function scheduleRefresh() {
      window.clearTimeout(refreshTimer);
      refreshTimer = window.setTimeout(() => void refreshLive(), 250);
    }

    function handleEvent(event: ChronicleEvent) {
      if (event.position <= cursor.current) return;
      cursor.current = event.position;
      setEvents((current) => [event, ...current].slice(0, 40));
      setChronicle((current) => [{
        id: event.event_id,
        event_id: event.event_id,
        correlation_id: event.correlation_id,
        causation_id: event.causation_id,
        actor_type: event.actor_role,
        actor_id: null,
        event_type: event.event_type,
        aggregate_type: event.aggregate_type,
        aggregate_id: event.aggregate_id,
        payload_json: event.payload,
        payload_hash: "live",
        previous_hash: null,
        created_at: event.created_at,
      }, ...current.filter((record) => record.event_id !== event.event_id)].slice(0, 40));
      scheduleRefresh();
    }

    async function hydrate() {
      setConnection("CONNECTING");
      setError(null);
      const snapshot = await fetchSystemState();
      const [projectionStatus, inferenceStatus, history] = await Promise.all([
        fetchProjectionStatus(),
        fetchInferenceStatus(),
        fetchChronicleHistory(snapshot.position),
      ]);
      if (!active) return;
      setState(snapshot);
      setProjections(projectionStatus);
      setInference(inferenceStatus);
      setChronicle(history);
      setEvents([]);
      void fetchInceptions().then(setInceptions).catch(() => setInceptions(null));
      cursor.current = snapshot.position;
      setConnection("LIVE");
    }

    async function run() {
      let backoff = 1000;
      let needsHydrate = true;
      while (active) {
        try {
          if (needsHydrate) {
            await hydrate();
            needsHydrate = false;
          }
          setConnection("LIVE");
          const end = await streamChronicle(cursor.current, (event) => { backoff = 1000; handleEvent(event); }, controller.signal);
          if (!active) return;
          if (end === "resync") {
            setConnection("RESYNCING");
            needsHydrate = true;
            backoff = 1000;
            continue;
          }
          // Stream closed by server/proxy: reconnect from the cursor after the backoff below.
        } catch (failure) {
          if (!active) return;
          if (failure instanceof Error && failure.message === "AUTH_REQUIRED") return fail(failure, "AUTH_REQUIRED");
          setError(failure instanceof Error ? failure.message : "STREAM_ERROR");
          setConnection("ERROR");
        }
        await new Promise((resolve) => window.setTimeout(resolve, backoff));
        backoff = Math.min(backoff * 2, 15000);
      }
    }

    void run();
    return () => {
      active = false;
      window.clearTimeout(refreshTimer);
      refreshSeq.current += 1;
      controller.abort();
    };
  }, [authVersion, retryVersion, refreshLive]);

  async function handleLogout() {
    await logoutCreator();
    window.localStorage.removeItem("creation_conversation_id");
    setState(null);
    setProjections(null);
    setInference(null);
    setChronicle([]);
    setEvents([]);
    setInceptions(null);
    setAuthVersion((version) => version + 1);
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoginPending(true);
    setLoginError(null);
    try {
      await loginCreator(username, password);
      setPassword("");
      setAuthVersion((version) => version + 1);
    } catch (loginFailure) {
      const message = loginFailure instanceof Error ? loginFailure.message : "LOGIN_FAILED";
      setLoginError(
        message === "INVALID_CREDENTIALS" ? "Invalid username or password."
          : message === "RATE_LIMITED" ? "Too many attempts. Wait a moment and try again."
          : "Authentication service unavailable.",
      );
    } finally {
      setLoginPending(false);
    }
  }

  const selectedMission = state?.missions.find((mission) => ["executing", "distributed", "authorized"].includes(mission.status)) ?? state?.missions.at(-1);
  const missionTasks = useMemo(() => state?.tasks.filter((task) => task.mission_id === selectedMission?.id) ?? [], [state, selectedMission]);
  const pulseEntries = useMemo(() => Object.entries(state?.pulse ?? {}).slice(0, 8), [state]);
  const deusReady = Boolean(inference?.configured && inference.providers.some((provider) => provider.available));

  return (
    <main className="terminal">
      <header className="topbar">
        <div><span className="eyebrow">THE CREATION OS</span><h1>Living Cognitive Operating System</h1></div>
        <div className="top-status">
          <span className={`status ${connection.toLowerCase()}`}>{connection}</span>
          <span>Chronicle #{state?.position ?? "—"}</span>
          <span>{state?.generated_at ? formatStamp(state.generated_at) : "—"}</span>
          {connection !== "AUTH_REQUIRED" && <button type="button" className="logout-button" onClick={() => void handleLogout()}>Sign out</button>}
        </div>
      </header>

      {connection === "AUTH_REQUIRED" && (
        <section className="login-shell" aria-live="polite">
          <form className="login-panel" onSubmit={handleLogin}>
            <span className="eyebrow">SOVEREIGN CREATOR</span>
            <h2>Creator Access</h2>
            <p>Authenticate to enter the live operating surface.</p>
            <label>
              <span>Username</span>
              <input aria-label="Username" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required />
            </label>
            <label>
              <span>Password</span>
              <input aria-label="Password" autoComplete="current-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required />
            </label>
            {loginError && <div className="login-error">{loginError}</div>}
            <button type="submit" disabled={loginPending}>{loginPending ? "Authenticating…" : "Enter The Creation"}</button>
          </form>
        </section>
      )}
      {connection === "CONNECTING" && !state && <section className="loading-shell" role="status" aria-live="polite"><div className="skeleton skeleton-wide" /><div className="skeleton" /><span>Loading live system state…</span></section>}
      {error && connection === "ERROR" && <section className="error-banner" role="alert">Live state unavailable: {error} <button type="button" className="retry-button" onClick={() => setRetryVersion((version) => version + 1)}>Retry</button></section>}

      {!(connection === "AUTH_REQUIRED" && !state) && <>
      <section className="metrics">
        {[
          ["MISSIONS", state?.counts.missions], ["RUNNING", state?.counts.running_missions], ["TASKS", state?.counts.tasks],
          ["READY", state?.counts.ready_tasks], ["ACTIVE UNIVERSES", state?.counts.active_universes], ["ACTIVE AGENTS", state?.counts.active_agents],
          ["MEMORY", state?.memory.total], ["FAILED/BLOCKED", state?.counts.failed_tasks],
        ].map(([label, value]) => <article className="metric" key={String(label)}><span>{label}</span><strong>{value ?? "—"}</strong></article>)}
      </section>

      <section className="workspace">
        <aside className="panel hierarchy">
          <div className="panel-title">SYSTEM HIERARCHY</div>
          <ol className="tree">
            {["CREATOR", "DEUS", "SOPHIA", "ROCKMAM", "INCEPTION", "CENTRAL CORE", "TREE CORE"].map((name) => <li key={name}>{name}</li>)}
          </ol>
          <div className="panel-title secondary">MISSIONS</div>
          <div className="stack">
            {state?.missions.slice(-8).reverse().map((mission) => <div className="row" key={mission.id}><span>{mission.title}</span><b className={statusTone(mission.status)}>{mission.status}</b></div>)}
          </div>
        </aside>

        <section className="panel core">
          <div className="panel-title">LIVING CORE VISUALIZATION</div>
          <div className="core-map" aria-hidden="true">
            <div className="orbit orbit-a"><span>SOPHIA</span></div>
            <div className="orbit orbit-b"><span>ROCKMAM</span></div>
            <div className="deus">DEUS</div>
            {state?.universes.filter((u) => u.active).slice(0, 8).map((u, i) => <div className={`node node-${i}`} key={u.id}>{u.code.toUpperCase()}</div>)}
          </div>
          <div className="mission-focus">
            <span className="eyebrow">CURRENT MISSION</span>
            <h2>{selectedMission?.title ?? "No active mission"}</h2>
            <p>{selectedMission?.objective ?? "Waiting for an authorized mission."}</p>
            {selectedMission && <span className={`pill ${statusTone(selectedMission.status)}`}>{selectedMission.status}</span>}
          </div>
        </section>

        <aside className="panel right-rail">
          <div className="panel-title">UNIVERSES</div>
          <div className="stack">{state?.universes.map((u) => <div className="row" key={u.id}><span>{u.name}</span><b className={u.active ? "good" : "neutral"}>{u.active ? "ACTIVE" : "IDLE"}</b></div>)}</div>
          <div className="panel-title secondary">AGENTS</div>
          <div className="stack">{state?.agents.slice(0, 12).map((a) => <div className="row" key={a.id}><span>{a.name}</span><b className={a.active ? "good" : "neutral"}>{a.active ? "LIVE" : "OFF"}</b></div>)}</div>
          <div className="panel-title secondary">MEMORY LAYERS</div>
          <div className="memory-grid">{state && Object.entries(state.memory).filter(([k]) => k !== "total").map(([k, value]) => <div key={k}><span>{k}</span><strong>{value}</strong></div>)}</div>
        </aside>
      </section>

      <section className="lower-grid lower-grid-primary">
        <article className="panel"><div className="panel-title">CHRONICLE</div><div className="event-list" tabIndex={0} role="region" aria-label="Chronicle events">{chronicle.length ? chronicle.map((event) => <div className="event" key={event.event_id}><time>{formatStamp(event.created_at)}</time><span>{event.event_type}</span><small>{event.aggregate_type}</small></div>) : <div className="empty">Chronicle has no persisted events.</div>}</div></article>
        <article className="panel"><div className="panel-title">PULSE</div><div className="stack">{pulseEntries.length ? pulseEntries.map(([name, metric]) => <div className="row" key={name}><span>{name}</span><b className="good">{String(metric.value)}</b></div>) : <div className="empty">No persisted Pulse metrics.</div>}</div></article>
        <article className="panel"><div className="panel-title">TASK DAG</div><div className="dag">{missionTasks.length ? missionTasks.map((task, i) => <div className="dag-item" key={task.id}><span>{i + 1}</span><div><strong>{task.status}</strong><small>{task.attempt_count}/{task.max_attempts} attempts</small></div></div>) : <div className="empty">No task graph for selected mission.</div>}</div></article>
        <article className="panel"><div className="panel-title">SYSTEM EVENTS</div><div className="event-list" tabIndex={0} role="region" aria-label="Live system events">{events.length ? events.map((event) => <div className="event" key={event.event_id}><time>#{event.position}</time><span>{event.event_type}</span><small>{event.aggregate_type}</small></div>) : <div className="empty">No new events since connection.</div>}</div></article>
      </section>

      <section className="lower-grid lower-grid-secondary">
        <DecisionsPanel inceptions={inceptions} missions={state?.missions ?? []} onChanged={() => void refreshLive()} />
        <CreatorConsole key={authVersion} enabled={deusReady} />
        <article className="panel projections-panel"><div className="panel-title">PROJECTIONS</div><div className="stack">{projections?.projections.map((projection) => <div className="row" key={projection.name}><span>{projection.name}</span><b className={statusTone(projection.status)}>{projection.status}{projection.lag ? ` · lag ${projection.lag}` : ""}</b></div>)}</div></article>
        <article className="panel inference-panel">
          <div className="panel-title">INFERENCE FABRIC</div>
          {!inference ? <div className="empty">Inference status unavailable.</div> : !inference.configured ? (
            <div className="stack"><div className="row"><span>{inference.configured_provider || "none"}</span><b className="warn">UNCONFIGURED</b></div></div>
          ) : (
            <div className="stack">
              {inference.providers.map((provider) => <div className="inference-provider" key={provider.provider}>
                <div className="row"><span>{provider.provider}</span><b className={statusTone(provider.available ? "AVAILABLE" : "UNAVAILABLE")}>{provider.available ? "AVAILABLE" : "UNAVAILABLE"}</b></div>
                {provider.detail && <small>{provider.detail}</small>}
                {provider.models.map((model) => <div className="row" key={`${provider.provider}:${model.model}`}>
                  <span><span>{model.model}</span><small>{model.capabilities.join(" · ")}</small></span>
                  <b className="neutral">{model.cost_tier}</b>
                </div>)}
              </div>)}
            </div>
          )}
        </article>
      </section>
      </>}
    </main>
  );
}

export default App;
