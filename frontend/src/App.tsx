import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, getProjectionStatus, getSystemState, login, streamChronicle } from "./api";
import type { ChronicleEvent, ProjectionStatus, Session, SystemState, Task } from "./types";

const SESSION_KEY = "creation-session";
const MAX_EVENTS = 80;

function readSession(): Session | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

function saveSession(session: Session | null) {
  if (session) sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
  else sessionStorage.removeItem(SESSION_KEY);
}

function time(value?: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(
    new Date(value),
  );
}

function statusClass(status: string) {
  const normalized = status.toLowerCase();
  if (["healthy", "current", "active", "succeeded", "manifested", "executing", "running"].includes(normalized)) {
    return "good";
  }
  if (["failed", "blocked", "invalid", "cancelled", "error"].includes(normalized)) return "bad";
  if (["lagging", "pending", "ready", "authorized", "distributed", "resyncing"].includes(normalized)) return "warn";
  return "neutral";
}

function Metric({ label, value, detail }: { label: string; value: string | number; detail?: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail ? <small>{detail}</small> : null}
    </div>
  );
}

function Panel({ title, meta, children, className = "" }: { title: string; meta?: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={`panel ${className}`}>
      <header className="panel-header">
        <h2>{title}</h2>
        {meta ? <span>{meta}</span> : null}
      </header>
      <div className="panel-body">{children}</div>
    </section>
  );
}

function Login({ onAuthenticated }: { onAuthenticated: (session: Session) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const next = await login(username, password);
      saveSession(next);
      onAuthenticated(next);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha de autenticação");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-shell">
      <form className="login-card" onSubmit={submit}>
        <div className="sigil" aria-hidden="true">◉</div>
        <p className="eyebrow">THE CREATION OS</p>
        <h1>Creator Interface</h1>
        <p className="login-copy">Autentique-se para abrir o estado operacional vivo. Nenhuma telemetria é simulada.</p>
        <label>
          Creator
          <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required />
        </label>
        <label>
          Credencial
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required />
        </label>
        {error ? <p className="auth-error" role="alert">{error}</p> : null}
        <button disabled={busy}>{busy ? "AUTENTICANDO" : "ENTRAR"}</button>
      </form>
    </main>
  );
}

function LivingCore({ state }: { state: SystemState }) {
  const universes = state.universes.slice(0, 8);
  const activeAgents = state.agents.filter((agent) => agent.active).slice(0, 12);
  return (
    <div className="living-core" aria-label="Living Core Visualization">
      <div className="core-grid" aria-hidden="true" />
      <div className="orbit orbit-a" aria-hidden="true" />
      <div className="orbit orbit-b" aria-hidden="true" />
      <div className="deus-node">
        <span>DEUS</span>
        <small>INTERFACE</small>
      </div>
      <div className="trinity sophia"><b>SOPHIA</b><small>WISDOM</small></div>
      <div className="trinity rockmam"><b>ROCKMAM</b><small>SYNTHESIS</small></div>
      {universes.map((universe, index) => {
        const angle = (index / Math.max(universes.length, 1)) * Math.PI * 2;
        const x = 50 + Math.cos(angle) * 38;
        const y = 50 + Math.sin(angle) * 36;
        return (
          <div
            className={`universe-node ${universe.active ? "active" : ""}`}
            key={universe.id}
            style={{ left: `${x}%`, top: `${y}%` }}
            title={`${universe.name}: ${universe.active ? "active" : "inactive"}`}
          >
            <i />
            <span>{universe.code.toUpperCase()}</span>
          </div>
        );
      })}
      <div className="agent-cloud">
        {activeAgents.map((agent) => <span key={agent.id}>{agent.code}</span>)}
      </div>
    </div>
  );
}

function TaskDag({ tasks }: { tasks: Task[] }) {
  if (!tasks.length) return <div className="empty">Nenhuma task persistida.</div>;
  return (
    <div className="dag-list">
      {tasks.slice(-12).map((task, index) => (
        <div className="dag-row" key={task.id}>
          <span className="dag-index">{String(index + 1).padStart(2, "0")}</span>
          <div className="dag-track"><i className={statusClass(task.status)} /></div>
          <code>{task.id.slice(0, 8)}</code>
          <span className={`badge ${statusClass(task.status)}`}>{task.status}</span>
          <small>{task.attempt_count}/{task.max_attempts}</small>
        </div>
      ))}
    </div>
  );
}

function Operations({ session, onLogout }: { session: Session; onLogout: () => void }) {
  const [state, setState] = useState<SystemState | null>(null);
  const [projections, setProjections] = useState<ProjectionStatus | null>(null);
  const [events, setEvents] = useState<ChronicleEvent[]>([]);
  const [connection, setConnection] = useState<"CONNECTING" | "LIVE" | "RESYNCING" | "DEGRADED">("CONNECTING");
  const [error, setError] = useState("");
  const cursor = useRef(0);
  const generation = useRef(0);

  const load = useCallback(async () => {
    const [nextState, nextProjections] = await Promise.all([
      getSystemState(session.accessToken),
      getProjectionStatus(session.accessToken),
    ]);
    cursor.current = Math.max(cursor.current, nextState.position);
    setState(nextState);
    setProjections(nextProjections);
    setError("");
  }, [session.accessToken]);

  useEffect(() => {
    let mounted = true;
    const abort = new AbortController();
    generation.current += 1;
    const currentGeneration = generation.current;

    async function run() {
      try {
        await load();
        if (!mounted) return;
        setConnection("LIVE");
        await streamChronicle(
          session.accessToken,
          cursor.current,
          abort.signal,
          (event) => {
            if (!mounted || generation.current !== currentGeneration) return;
            cursor.current = event.position;
            setEvents((current) => [event, ...current].slice(0, MAX_EVENTS));
            void load();
          },
          () => {
            if (!mounted) return;
            setConnection("RESYNCING");
            void load().then(() => setConnection("LIVE"));
          },
        );
      } catch (cause) {
        if (abort.signal.aborted || !mounted) return;
        if (cause instanceof ApiError && cause.status === 401) {
          saveSession(null);
          onLogout();
          return;
        }
        setConnection("DEGRADED");
        setError(cause instanceof Error ? cause.message : "Falha no estado live");
      }
    }

    void run();
    const interval = window.setInterval(() => void load().catch(() => setConnection("DEGRADED")), 10_000);
    return () => {
      mounted = false;
      abort.abort();
      window.clearInterval(interval);
    };
  }, [load, onLogout, session.accessToken]);

  const projectionLag = useMemo(
    () => projections?.projections.reduce((sum, item) => sum + (item.lag ?? 0), 0) ?? 0,
    [projections],
  );

  if (!state) {
    return <main className="boot"><div className="boot-ring" /><p>SYNCING LIVING STATE</p>{error ? <small>{error}</small> : null}</main>;
  }

  const recentMissions = [...state.missions].reverse().slice(0, 8);
  const recentTasks = [...state.tasks].reverse();
  const pulseEntries = Object.entries(state.pulse).slice(0, 10);

  return (
    <main className="terminal">
      <header className="topbar">
        <div className="brand"><span className="brand-mark">◉</span><div><b>THE CREATION OS</b><small>LIVING COGNITIVE OPERATING SYSTEM</small></div></div>
        <div className="system-strip">
          <span><i className={connection === "LIVE" ? "good" : "warn"} />{connection}</span>
          <span>CHRONICLE <b>{state.position}</b></span>
          <span>PROJECTION LAG <b>{projectionLag}</b></span>
          <span>UTC <b>{time(state.generated_at)}</b></span>
        </div>
        <button className="ghost" onClick={() => { saveSession(null); onLogout(); }}>SAIR</button>
      </header>

      <div className="metric-row">
        <Metric label="MISSIONS" value={state.counts.missions} detail={`${state.counts.running_missions} em execução`} />
        <Metric label="TASKS" value={state.counts.tasks} detail={`${state.counts.ready_tasks} ready · ${state.counts.running_tasks} running`} />
        <Metric label="UNIVERSES" value={state.counts.active_universes} detail={`${state.universes.length} registrados`} />
        <Metric label="AGENTS" value={state.counts.active_agents} detail={`${state.agents.length} registrados`} />
        <Metric label="MEMORY" value={state.memory.total} detail={`${state.memory.conscious} conscious`} />
        <Metric label="FAILURES" value={state.counts.failed_tasks} detail="tasks failed / blocked" />
      </div>

      <div className="operations-grid">
        <div className="left-stack">
          <Panel title="SYSTEM HIERARCHY" meta="REAL STATE">
            <div className="hierarchy">
              <div className="hierarchy-root">CREATOR</div><i />
              <div>DEUS <small>interface</small></div><i />
              <div>SOPHIA <small>assessment</small></div><i />
              <div>ROCKMAM <small>synthesis</small></div><i />
              <div>INCEPTION → MISSION → DAG</div><i />
              <div>UNIVERSES → AGENTS</div>
            </div>
          </Panel>
          <Panel title="MISSIONS" meta={`${state.counts.running_missions} ACTIVE`}>
            <div className="mission-list">
              {recentMissions.length ? recentMissions.map((mission) => (
                <article key={mission.id}>
                  <div><strong>{mission.title}</strong><small>{mission.objective}</small></div>
                  <span className={`badge ${statusClass(mission.status)}`}>{mission.status}</span>
                </article>
              )) : <div className="empty">Nenhuma missão persistida.</div>}
            </div>
          </Panel>
        </div>

        <Panel title="LIVING CORE VISUALIZATION" meta={`POSITION ${state.position}`} className="core-panel">
          <LivingCore state={state} />
        </Panel>

        <div className="right-stack">
          <Panel title="UNIVERSES" meta={`${state.counts.active_universes} ACTIVE`}>
            <div className="entity-list">
              {state.universes.map((universe) => <div key={universe.id}><i className={universe.active ? "good" : "neutral"} /><span>{universe.name}<small>{universe.code}</small></span></div>)}
              {!state.universes.length ? <div className="empty">Nenhum universo.</div> : null}
            </div>
          </Panel>
          <Panel title="AGENTS" meta={`${state.counts.active_agents} ACTIVE`}>
            <div className="entity-list compact">
              {state.agents.slice(0, 12).map((agent) => <div key={agent.id}><i className={agent.active ? "good" : "neutral"} /><span>{agent.name}<small>{agent.code}</small></span></div>)}
            </div>
          </Panel>
          <Panel title="MEMORY LAYERS" meta={`${state.memory.total} RECORDS`}>
            <div className="memory-grid">
              <span>CONVERSATION<b>{state.memory.conversation}</b></span><span>MISSION<b>{state.memory.mission}</b></span>
              <span>UNIVERSE<b>{state.memory.universe}</b></span><span>CONSCIOUS<b>{state.memory.conscious}</b></span>
            </div>
          </Panel>
        </div>

        <Panel title="CHRONICLE" meta={`${events.length} LIVE EVENTS`} className="chronicle-panel">
          <div className="chronicle-list">
            {events.length ? events.map((event) => (
              <div key={event.event_id}><time>{time(event.created_at)}</time><code>{event.position}</code><strong>{event.event_type}</strong><span>{event.aggregate_type}</span></div>
            )) : <div className="empty">Conectado. Aguardando novos eventos do Chronicle.</div>}
          </div>
        </Panel>

        <Panel title="PULSE" meta={connection} className="pulse-panel">
          <div className="pulse-visual"><div className="pulse-line" /><div className="pulse-beat" /></div>
          <div className="pulse-values">
            {pulseEntries.length ? pulseEntries.map(([name, item]) => <span key={name}><small>{name}</small><b>{typeof item.value === "object" ? "LIVE" : String(item.value)}</b></span>) : <span><small>PULSE</small><b>NO SAMPLES</b></span>}
          </div>
        </Panel>

        <Panel title="TASK DAG" meta={`${state.counts.tasks} TASKS`} className="dag-panel"><TaskDag tasks={recentTasks} /></Panel>

        <Panel title="SYSTEM EVENTS" meta={projections ? `HEAD ${projections.chronicle_head}` : "SYNC"} className="events-panel">
          <div className="projection-list">
            {projections?.projections.map((projection) => (
              <div key={projection.name}><strong>{projection.name}</strong><span className={`badge ${statusClass(projection.status)}`}>{projection.status}</span><small>pos {projection.position ?? "—"} · lag {projection.lag ?? "—"}</small></div>
            ))}
          </div>
          {error ? <p className="inline-error">{error}</p> : null}
        </Panel>
      </div>

      <footer className="telemetry-strip">
        <span>STATE <b>{state.projection.toUpperCase()}</b></span>
        <span>GENERATED <b>{time(state.generated_at)}</b></span>
        <span>READY TASKS <b>{state.counts.ready_tasks}</b></span>
        <span>RUNNING TASKS <b>{state.counts.running_tasks}</b></span>
        <span>FAILED/BLOCKED <b>{state.counts.failed_tasks}</b></span>
        <span className={connection === "LIVE" ? "good-text" : "warn-text"}>● {connection}</span>
      </footer>
    </main>
  );
}

export default function App() {
  const [session, setSession] = useState<Session | null>(() => readSession());
  if (!session) return <Login onAuthenticated={setSession} />;
  return <Operations session={session} onLogout={() => setSession(null)} />;
}
