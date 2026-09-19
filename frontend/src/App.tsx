import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  fetchChronicleHistory,
  fetchInferenceStatus,
  fetchProjectionStatus,
  fetchSystemState,
  loginCreator,
  streamChronicle,
} from "./api";
import { CreatorConsole } from "./CreatorConsole";
import type {
  ChronicleEvent,
  ChronicleRecord,
  InferenceStatusSnapshot,
  ProjectionStatus,
  SystemState,
} from "./types";

type ConnectionState = "CONNECTING" | "LIVE" | "RESYNCING" | "AUTH_REQUIRED" | "ERROR";

function statusTone(status: string): string {
  const value = status.toUpperCase();
  if (["MANIFESTED", "SUCCEEDED", "CURRENT", "ACTIVE", "HEALTHY", "AVAILABLE", "LIVE"].includes(value)) return "good";
  if (["FAILED", "BLOCKED", "INVALID", "DEGRADED", "UNAVAILABLE", "ERROR"].includes(value)) return "bad";
  if (["RUNNING", "EXECUTING", "DISTRIBUTED", "READY", "LAGGING", "UNCONFIGURED", "CONNECTING", "RESYNCING"].includes(value)) return "warn";
  return "neutral";
}

function Panel({
  title,
  meta,
  className = "",
  children,
}: {
  title: string;
  meta?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <article className={`panel ${className}`}>
      <header className="panel-head">
        <span>{title}</span>
        {meta && <span className="panel-meta">{meta}</span>}
      </header>
      {children}
    </article>
  );
}

function Empty({ children = "NO DATA" }: { children?: ReactNode }) {
  return <div className="empty-state"><span className="empty-dot" />{children}</div>;
}

function App() {
  const [state, setState] = useState<SystemState | null>(null);
  const [projections, setProjections] = useState<ProjectionStatus | null>(null);
  const [inference, setInference] = useState<InferenceStatusSnapshot | null>(null);
  const [chronicle, setChronicle] = useState<ChronicleRecord[]>([]);
  const [events, setEvents] = useState<ChronicleEvent[]>([]);
  const [connection, setConnection] = useState<ConnectionState>("CONNECTING");
  const [error, setError] = useState<string | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loginPending, setLoginPending] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [authVersion, setAuthVersion] = useState(0);
  const [retryVersion, setRetryVersion] = useState(0);
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
        void streamChronicle(
          cursor.current,
          {
            onEvent: (event) => {
              cursor.current = event.position;
              setEvents((current) => [event, ...current].slice(0, 48));
              setChronicle((current) => [
                {
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
                },
                ...current,
              ].slice(0, 48));
              void Promise.all([fetchSystemState(), fetchProjectionStatus(), fetchInferenceStatus()]).then(
                ([next, nextProjections, nextInference]) => {
                  if (!active) return;
                  setState(next);
                  setProjections(nextProjections);
                  setInference(nextInference);
                },
              );
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
          },
          controller.signal,
        );
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

  const selectedMission =
    state?.missions.find((mission) => ["executing", "distributed", "authorized"].includes(mission.status)) ??
    state?.missions.at(-1);
  const missionTasks = useMemo(
    () => state?.tasks.filter((task) => task.mission_id === selectedMission?.id) ?? [],
    [state, selectedMission],
  );
  const pulseEntries = useMemo(() => Object.entries(state?.pulse ?? {}).slice(0, 10), [state]);
  const activeUniverses = useMemo(() => state?.universes.filter((universe) => universe.active) ?? [], [state]);
  const deusReady = Boolean(inference?.configured && inference.providers.some((provider) => provider.available));
  const provider = inference?.providers.find((item) => item.available) ?? inference?.providers[0];

  const metrics = [
    ["MISSIONS", state?.counts.missions, state?.counts.running_missions ? `${state.counts.running_missions} RUNNING` : "IDLE"],
    ["TASKS", state?.counts.tasks, state?.counts.ready_tasks ? `${state.counts.ready_tasks} READY` : "NO QUEUE"],
    ["UNIVERSES", state?.counts.active_universes, `${state?.universes.length ?? 0} TOTAL`],
    ["AGENTS", state?.counts.active_agents, `${state?.agents.length ?? 0} TOTAL`],
    ["MEMORY", state?.memory.total, "RECORDS"],
    ["CHRONICLE", state?.position, "HEAD"],
    ["PROJECTIONS", projections?.projections.filter((item) => item.status === "CURRENT").length, `/${projections?.projections.length ?? 0} CURRENT`],
    ["INFERENCE", deusReady ? "ON" : "OFF", provider?.provider?.toUpperCase() ?? "UNCONFIGURED"],
  ] as const;

  return (
    <main className="terminal">
      <header className="command-bar">
        <div className="brand-block">
          <span className="brand-mark">TCO</span>
          <div>
            <span className="eyebrow">THE CREATION OS</span>
            <h1>Living Cognitive Operating System</h1>
          </div>
        </div>
        <div className="command-status">
          <div><span>RUNTIME</span><strong className="good">LOCAL</strong></div>
          <div><span>LINK</span><strong className={statusTone(connection)}>{connection}</strong></div>
          <div><span>CHRONICLE</span><strong>#{state?.position ?? "—"}</strong></div>
          <div><span>DEUS</span><strong className={deusReady ? "good" : "warn"}>{deusReady ? "READY" : "WAIT"}</strong></div>
          <div><span>UTC</span><strong>{state?.generated_at ? new Date(state.generated_at).toISOString().slice(11, 19) : "—"}</strong></div>
        </div>
      </header>

      {connection === "AUTH_REQUIRED" && (
        <section className="login-shell" aria-live="polite">
          <form className="login-panel" onSubmit={handleLogin}>
            <span className="eyebrow">SOVEREIGN CREATOR</span>
            <h2>Creator Access</h2>
            <p>Authenticate to enter the living operating surface.</p>
            <label>
              <span>Username</span>
              <input aria-label="Username" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required />
            </label>
            <label>
              <span>Password</span>
              <input aria-label="Password" autoComplete="current-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required />
            </label>
            {loginError && <div className="login-error">{loginError}</div>}
            <button type="submit" disabled={loginPending}>{loginPending ? "AUTHENTICATING…" : "ENTER THE CREATION"}</button>
          </form>
        </section>
      )}

      {connection === "CONNECTING" && !state && (
        <section className="loading-shell" role="status" aria-live="polite">
          <div className="skeleton skeleton-wide" />
          <div className="skeleton" />
          <span>SYNCING LIVING STATE…</span>
        </section>
      )}

      {error && connection === "ERROR" && (
        <section className="error-banner" role="alert">
          <span>LIVE STATE UNAVAILABLE · {error}</span>
          <button type="button" className="retry-button" onClick={() => setRetryVersion((version) => version + 1)}>RETRY</button>
        </section>
      )}

      <section className="telemetry-ribbon" aria-label="System telemetry">
        {metrics.map(([label, value, detail]) => (
          <div className="telemetry-cell" key={label}>
            <span>{label}</span>
            <strong>{value ?? "—"}</strong>
            <small>{detail}</small>
          </div>
        ))}
      </section>

      <section className="operations-grid">
        <aside className="left-column">
          <Panel title="SYSTEM HIERARCHY" meta={<span className="good">LIVE TREE</span>} className="hierarchy-panel">
            <div className="hierarchy-tree">
              {[
                ["CREATOR", "SOVEREIGN"],
                ["DEUS", deusReady ? "READY" : "INFERENCE"],
                ["SOPHIA", "COGNITION"],
                ["ROCKMAM", "EXECUTION"],
                ["INCEPTION", "INTENT"],
                ["CENTRAL CORE", "ORCHESTRATION"],
                ["TREE CORE", "DISTRIBUTION"],
              ].map(([name, role], index) => (
                <div className={`hierarchy-node level-${index}`} key={name}>
                  <i />
                  <span>{name}</span>
                  <small>{role}</small>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="MISSIONS" meta={<span>{state?.missions.length ?? 0}</span>} className="missions-panel">
            <div className="dense-list">
              {state?.missions.length ? state.missions.slice(-10).reverse().map((mission) => (
                <div className="dense-row" key={mission.id}>
                  <div><strong>{mission.title}</strong><small>{mission.objective}</small></div>
                  <span className={statusTone(mission.status)}>{mission.status}</span>
                </div>
              )) : <Empty>NO MISSIONS</Empty>}
            </div>
          </Panel>
        </aside>

        <section className="center-column">
          <Panel title="LIVING CORE VISUALIZATION" meta={<span className={deusReady ? "good" : "warn"}>{deusReady ? "COGNITIVE FABRIC ONLINE" : "COGNITIVE FABRIC WAITING"}</span>} className="living-core-panel">
            <div className="core-stage">
              <div className="grid-plane" />
              <div className="core-ring ring-1" />
              <div className="core-ring ring-2" />
              <div className="core-ring ring-3" />
              <div className="axis axis-x" />
              <div className="axis axis-y" />

              <div className="core-satellite sophia"><b>SOPHIA</b><small>WISDOM</small></div>
              <div className="core-satellite rockmam"><b>ROCKMAM</b><small>ACTION</small></div>
              <div className="core-satellite inception"><b>INCEPTION</b><small>INTENT GATE</small></div>

              <div className={`deus-core ${deusReady ? "online" : ""}`}>
                <span className="core-pulse" />
                <strong>DEUS</strong>
                <small>{deusReady ? "READY" : "WAITING"}</small>
              </div>

              {activeUniverses.slice(0, 8).map((universe, index) => (
                <div className={`universe-node universe-${index}`} key={universe.id}>
                  <span>{universe.code.toUpperCase()}</span>
                  <small>UNIVERSE</small>
                </div>
              ))}

              {!activeUniverses.length && (
                <div className="core-empty">
                  <span>NO ACTIVE UNIVERSES</span>
                  <small>Runtime is connected; domain topology has not been populated.</small>
                </div>
              )}

              <div className="core-status-strip">
                <div><span>MISSION</span><strong>{selectedMission?.title ?? "NO ACTIVE MISSION"}</strong></div>
                <div><span>STATE</span><strong className={selectedMission ? statusTone(selectedMission.status) : "neutral"}>{selectedMission?.status ?? "IDLE"}</strong></div>
                <div><span>TASKS</span><strong>{missionTasks.length}</strong></div>
              </div>
            </div>
          </Panel>
        </section>

        <aside className="right-column">
          <Panel title="UNIVERSES" meta={<span>{state?.universes.length ?? 0}</span>} className="rail-panel">
            <div className="dense-list compact">
              {state?.universes.length ? state.universes.map((universe) => (
                <div className="dense-row" key={universe.id}>
                  <div><strong>{universe.name}</strong><small>{universe.code}</small></div>
                  <span className={universe.active ? "good" : "neutral"}>{universe.active ? "ACTIVE" : "IDLE"}</span>
                </div>
              )) : <Empty>NO UNIVERSES</Empty>}
            </div>
          </Panel>

          <Panel title="AGENTS" meta={<span>{state?.agents.length ?? 0}</span>} className="rail-panel agents-panel">
            <div className="dense-list compact">
              {state?.agents.length ? state.agents.slice(0, 14).map((agent) => (
                <div className="dense-row" key={agent.id}>
                  <div><strong>{agent.name}</strong><small>{agent.code}</small></div>
                  <span className={agent.active ? "good" : "neutral"}>{agent.active ? "LIVE" : "OFF"}</span>
                </div>
              )) : <Empty>NO AGENTS</Empty>}
            </div>
          </Panel>

          <Panel title="MEMORY LAYERS" meta={<span>{state?.memory.total ?? 0}</span>} className="memory-panel">
            <div className="memory-matrix">
              {state && Object.entries(state.memory).filter(([key]) => key !== "total").map(([key, value]) => (
                <div key={key}><span>{key}</span><strong>{value}</strong><i style={{ width: `${Math.min(100, value * 8)}%` }} /></div>
              ))}
            </div>
          </Panel>
        </aside>
      </section>

      <section className="systems-grid">
        <Panel title="CHRONICLE" meta={<span>HEAD #{state?.position ?? "—"}</span>} className="chronicle-panel">
          <div className="event-table">
            {chronicle.length ? chronicle.slice().reverse().slice(0, 14).map((event) => (
              <div className="event-row" key={event.event_id}>
                <time>{new Date(event.created_at).toLocaleTimeString()}</time>
                <span>{event.event_type}</span>
                <small>{event.aggregate_type}</small>
              </div>
            )) : <Empty>NO CHRONICLE EVENTS</Empty>}
          </div>
        </Panel>

        <Panel title="PULSE" meta={<span className={connection === "LIVE" ? "good" : "warn"}>{connection}</span>} className="pulse-panel">
          <div className="pulse-scope">
            <div className="pulse-orb"><span /></div>
            <div className="pulse-readings">
              {pulseEntries.length ? pulseEntries.map(([name, metric]) => (
                <div key={name}><span>{name}</span><strong>{typeof metric.value === "object" ? "LIVE" : String(metric.value)}</strong></div>
              )) : <Empty>NO PULSE METRICS</Empty>}
            </div>
          </div>
        </Panel>

        <Panel title="TASK DAG" meta={<span>{missionTasks.length} NODES</span>} className="dag-panel">
          <div className="dag-flow">
            {missionTasks.length ? missionTasks.map((task, index) => (
              <div className="dag-node" key={task.id}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <div><strong>{task.status}</strong><small>{task.attempt_count}/{task.max_attempts} ATTEMPTS</small></div>
              </div>
            )) : <Empty>NO TASK GRAPH</Empty>}
          </div>
        </Panel>

        <Panel title="SYSTEM EVENTS" meta={<span>{events.length} LIVE</span>} className="system-events-panel">
          <div className="event-table">
            {events.length ? events.slice(0, 14).map((event) => (
              <div className="event-row" key={event.event_id}>
                <time>#{event.position}</time>
                <span>{event.event_type}</span>
                <small>{event.aggregate_type}</small>
              </div>
            )) : <Empty>WAITING FOR LIVE EVENTS</Empty>}
          </div>
        </Panel>
      </section>

      <section className="command-deck">
        <CreatorConsole enabled={deusReady} />

        <div className="deck-side">
          <Panel title="PROJECTIONS" meta={<span>READ MODELS</span>} className="projection-panel">
            <div className="projection-list">
              {projections?.projections.length ? projections.projections.map((projection) => (
                <div key={projection.name}>
                  <span>{projection.name}</span>
                  <strong className={statusTone(projection.status)}>{projection.status}</strong>
                  <small>{projection.position == null ? "NO CHECKPOINT" : `#${projection.position}`}{projection.lag ? ` · LAG ${projection.lag}` : ""}</small>
                </div>
              )) : <Empty>NO PROJECTION DATA</Empty>}
            </div>
          </Panel>

          <Panel title="INFERENCE FABRIC" meta={<span>{provider?.provider?.toUpperCase() ?? "NONE"}</span>} className="inference-panel">
            {inference?.configured ? (
              <div className="inference-fabric">
                {inference.providers.map((item) => (
                  <div className="provider-card" key={item.provider}>
                    <div><strong>{item.provider}</strong><span className={item.available ? "good" : "bad"}>{item.available ? "AVAILABLE" : "UNAVAILABLE"}</span></div>
                    {item.detail && <small>{item.detail}</small>}
                    {item.models.map((model) => (
                      <div className="model-row" key={`${item.provider}:${model.model}`}>
                        <span>{model.model}</span><small>{model.capabilities.join(" · ") || "TEXT"}</small>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            ) : <Empty>INFERENCE UNCONFIGURED</Empty>}
          </Panel>
        </div>
      </section>

      <footer className="system-footer">
        <span>THE CREATION OS · LOCAL RUNTIME</span>
        <span>DB/REDIS PRIVATE</span>
        <span>SEMANTIC CACHE SHADOW</span>
        <span>SSE {connection === "LIVE" ? "LINKED" : connection}</span>
        <span>{state?.generated_at ? new Date(state.generated_at).toLocaleString() : "NO SNAPSHOT"}</span>
      </footer>
    </main>
  );
}

export default App;
