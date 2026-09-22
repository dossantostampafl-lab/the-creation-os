import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import { fetchChronicleHistory, fetchInferenceStatus, fetchProjectionStatus, fetchSystemState, loginCreator, streamChronicle } from "./api";
import { Cosmos } from "./Cosmos";
import type { CosmosMood } from "./Cosmos";
import { CreatorConsole } from "./CreatorConsole";
import type { ChronicleEvent, ChronicleRecord, InferenceStatusSnapshot, ProjectionStatus, SystemState } from "./types";

function statusTone(status: string): string {
  const value = status.toUpperCase();
  if (["MANIFESTED", "SUCCEEDED", "CURRENT", "ACTIVE", "HEALTHY", "AVAILABLE"].includes(value)) return "good";
  if (["FAILED", "BLOCKED", "INVALID", "DEGRADED", "UNAVAILABLE"].includes(value)) return "bad";
  if (["RUNNING", "EXECUTING", "DISTRIBUTED", "READY", "LAGGING", "UNCONFIGURED"].includes(value)) return "warn";
  return "neutral";
}

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
  const [mood, setMood] = useState<CosmosMood>("idle");
  const [vitalsOpen, setVitalsOpen] = useState(false);
  const cursor = useRef(0);

  useEffect(() => {
    let active = true;
    let controller = new AbortController();

    async function hydrate() {
      try {
        setConnection("CONNECTING");
        setError(null);
        const [snapshot, projectionStatus, inferenceStatus, history] = await Promise.all([
          fetchSystemState(),
          fetchProjectionStatus(),
          fetchInferenceStatus(),
          fetchChronicleHistory(),
        ]);
        if (!active) return;
        setState(snapshot);
        setProjections(projectionStatus);
        setInference(inferenceStatus);
        setChronicle(history);
        cursor.current = snapshot.position;
        setConnection("LIVE");
        controller.abort();
        controller = new AbortController();
        void streamChronicle(cursor.current, {
          onEvent: (event) => {
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
            }, ...current].slice(0, 40));
            void Promise.all([fetchSystemState(), fetchProjectionStatus(), fetchInferenceStatus()]).then(([next, nextProjections, nextInference]) => {
              if (!active) return;
              setState(next);
              setProjections(nextProjections);
              setInference(nextInference);
            });
          },
          onResync: () => {
            setConnection("RESYNCING");
            void hydrate();
          },
          onError: (streamError) => {
            const message = streamError instanceof Error ? streamError.message : "STREAM_ERROR";
            setError(message);
            setConnection(message === "AUTH_REQUIRED" ? "AUTH_REQUIRED" : "ERROR");
          },
        }, controller.signal);
      } catch (loadError) {
        const message = loadError instanceof Error ? loadError.message : "LOAD_ERROR";
        setError(message);
        setConnection(message === "AUTH_REQUIRED" ? "AUTH_REQUIRED" : "ERROR");
      }
    }

    void hydrate();
    return () => {
      active = false;
      controller.abort();
    };
  }, [authVersion, retryVersion]);

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
      setLoginError(message === "INVALID_CREDENTIALS" ? "Invalid username or password." : "Authentication service unavailable.");
    } finally {
      setLoginPending(false);
    }
  }

  const selectedMission = state?.missions.find((mission) => ["executing", "distributed", "authorized"].includes(mission.status)) ?? state?.missions.at(-1);
  const missionTasks = useMemo(() => state?.tasks.filter((task) => task.mission_id === selectedMission?.id) ?? [], [state, selectedMission]);
  const pulseEntries = useMemo(() => Object.entries(state?.pulse ?? {}).slice(0, 8), [state]);
  const deusReady = Boolean(inference?.configured && inference.providers.some((provider) => provider.available));
  const universes = useMemo(() => state?.universes.slice(0, 12) ?? [], [state]);

  return (
    <main className="universe">
      <Cosmos universes={universes} signal={events[0]?.position ?? 0} mood={mood} />

      <header className="cosmic-header">
        <div className="title">
          <span className="eyebrow">THE CREATION OS</span>
          <h1>Living Cognitive Operating System</h1>
        </div>
        <div className="top-status">
          <span className={`status ${connection.toLowerCase()}`}>{connection}</span>
          <span className="chronicle-position">Chronicle #{state?.position ?? "—"}</span>
          {state && (
            <button type="button" className="vitals-toggle" aria-expanded={vitalsOpen} aria-controls="system-vitals" onClick={() => setVitalsOpen((open) => !open)}>
              {vitalsOpen ? "Close vitals" : "System vitals"}
            </button>
          )}
        </div>
      </header>

      {selectedMission && (
        <div className="mission-whisper">
          <span className="eyebrow">CURRENT MISSION</span>
          <h2>{selectedMission.title}</h2>
          <span className={`pill ${statusTone(selectedMission.status)}`}>{selectedMission.status}</span>
        </div>
      )}

      {connection === "AUTH_REQUIRED" && (
        <section className="login-shell" aria-live="polite">
          <form className="login-panel" onSubmit={handleLogin}>
            <span className="eyebrow">SOVEREIGN CREATOR</span>
            <h2>Creator Access</h2>
            <p>Authenticate to enter the living universe.</p>
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
      {connection === "CONNECTING" && !state && <section className="loading-shell" role="status" aria-live="polite"><span className="loading-orb" />Loading live system state…</section>}
      {error && connection === "ERROR" && <section className="error-banner" role="alert">Live state unavailable: {error} <button type="button" className="retry-button" onClick={() => setRetryVersion((version) => version + 1)}>Retry</button></section>}

      {connection !== "AUTH_REQUIRED" && <CreatorConsole enabled={deusReady} onMoodChange={setMood} />}

      {vitalsOpen && state && (
        <aside className="vitals" id="system-vitals" aria-label="System vitals">
          <section className="metrics">
            {[
              ["MISSIONS", state.counts.missions], ["RUNNING", state.counts.running_missions], ["TASKS", state.counts.tasks],
              ["READY", state.counts.ready_tasks], ["ACTIVE UNIVERSES", state.counts.active_universes], ["ACTIVE AGENTS", state.counts.active_agents],
              ["MEMORY", state.memory.total], ["FAILED/BLOCKED", state.counts.failed_tasks],
            ].map(([label, value]) => <article className="metric" key={String(label)}><span>{label}</span><strong>{value}</strong></article>)}
          </section>

          <article className="panel"><div className="panel-title">SYSTEM HIERARCHY</div>
            <ol className="tree">{["CREATOR", "DEUS", "SOPHIA", "ROCKMAM", "INCEPTION", "CENTRAL CORE", "TREE CORE"].map((name) => <li key={name}>{name}</li>)}</ol>
          </article>
          <article className="panel"><div className="panel-title">MISSIONS</div>
            <div className="stack">{state.missions.slice(-8).reverse().map((mission) => <div className="row" key={mission.id}><span>{mission.title}</span><b className={statusTone(mission.status)}>{mission.status}</b></div>)}</div>
          </article>
          <article className="panel"><div className="panel-title">UNIVERSES</div>
            <div className="stack">{state.universes.map((u) => <div className="row" key={u.id}><span>{u.name}</span><b className={u.active ? "good" : "neutral"}>{u.active ? "ACTIVE" : "IDLE"}</b></div>)}</div>
          </article>
          <article className="panel"><div className="panel-title">AGENTS</div>
            <div className="stack">{state.agents.slice(0, 12).map((a) => <div className="row" key={a.id}><span>{a.name}</span><b className={a.active ? "good" : "neutral"}>{a.active ? "LIVE" : "OFF"}</b></div>)}</div>
          </article>
          <article className="panel"><div className="panel-title">MEMORY LAYERS</div>
            <div className="memory-grid">{Object.entries(state.memory).filter(([k]) => k !== "total").map(([k, value]) => <div key={k}><span>{k}</span><strong>{value}</strong></div>)}</div>
          </article>
          <article className="panel"><div className="panel-title">CHRONICLE</div><div className="event-list">{chronicle.length ? chronicle.map((event) => <div className="event" key={event.event_id}><time>{new Date(event.created_at).toLocaleTimeString()}</time><span>{event.event_type}</span><small>{event.aggregate_type}</small></div>) : <div className="empty">Chronicle has no persisted events.</div>}</div></article>
          <article className="panel system-events"><div className="panel-title">SYSTEM EVENTS</div><div className="event-list">{events.length ? events.map((event) => <div className="event" key={event.event_id}><time>#{event.position}</time><span>{event.event_type}</span><small>{event.aggregate_type}</small></div>) : <div className="empty">No new events since connection.</div>}</div></article>
          <article className="panel"><div className="panel-title">PULSE</div><div className="stack">{pulseEntries.length ? pulseEntries.map(([name, metric]) => <div className="row" key={name}><span>{name}</span><b className="good">{String(metric.value)}</b></div>) : <div className="empty">No persisted Pulse metrics.</div>}</div></article>
          <article className="panel"><div className="panel-title">TASK DAG</div><div className="dag">{missionTasks.length ? missionTasks.map((task, i) => <div className="dag-item" key={task.id}><span>{i + 1}</span><div><strong>{task.status}</strong><small>{task.attempt_count}/{task.max_attempts} attempts</small></div></div>) : <div className="empty">No task graph for selected mission.</div>}</div></article>
          <article className="panel"><div className="panel-title">PROJECTIONS</div><div className="stack">{projections?.projections.map((projection) => <div className="row" key={projection.name}><span>{projection.name}</span><b className={statusTone(projection.status)}>{projection.status}{projection.lag ? ` · lag ${projection.lag}` : ""}</b></div>)}</div></article>
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
        </aside>
      )}
    </main>
  );
}

export default App;
