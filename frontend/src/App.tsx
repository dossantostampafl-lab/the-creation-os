import { useEffect, useMemo, useRef, useState } from "react";
import { fetchChronicleHistory, fetchProjectionStatus, fetchSystemState, streamChronicle } from "./api";
import type { ChronicleEvent, ChronicleRecord, ProjectionStatus, SystemState } from "./types";

function statusTone(status: string): string {
  const value = status.toUpperCase();
  if (["MANIFESTED", "SUCCEEDED", "CURRENT", "ACTIVE", "HEALTHY"].includes(value)) return "good";
  if (["FAILED", "BLOCKED", "INVALID", "DEGRADED"].includes(value)) return "bad";
  if (["RUNNING", "EXECUTING", "DISTRIBUTED", "READY", "LAGGING"].includes(value)) return "warn";
  return "neutral";
}

function App() {
  const [state, setState] = useState<SystemState | null>(null);
  const [projections, setProjections] = useState<ProjectionStatus | null>(null);
  const [chronicle, setChronicle] = useState<ChronicleRecord[]>([]);
  const [events, setEvents] = useState<ChronicleEvent[]>([]);
  const [connection, setConnection] = useState<"CONNECTING" | "LIVE" | "RESYNCING" | "AUTH_REQUIRED" | "ERROR">("CONNECTING");
  const [error, setError] = useState<string | null>(null);
  const cursor = useRef(0);

  useEffect(() => {
    let active = true;
    let controller = new AbortController();

    async function hydrate() {
      try {
        setConnection("CONNECTING");
        setError(null);
        const [snapshot, projectionStatus, history] = await Promise.all([
          fetchSystemState(),
          fetchProjectionStatus(),
          fetchChronicleHistory(),
        ]);
        if (!active) return;
        setState(snapshot);
        setProjections(projectionStatus);
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
            void Promise.all([fetchSystemState(), fetchProjectionStatus()]).then(([next, nextProjections]) => {
              if (!active) return;
              setState(next);
              setProjections(nextProjections);
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
  }, []);

  const selectedMission = state?.missions.find((mission) => ["executing", "distributed", "authorized"].includes(mission.status)) ?? state?.missions.at(-1);
  const missionTasks = useMemo(() => state?.tasks.filter((task) => task.mission_id === selectedMission?.id) ?? [], [state, selectedMission]);
  const pulseEntries = useMemo(() => Object.entries(state?.pulse ?? {}).slice(0, 8), [state]);

  return (
    <main className="terminal">
      <header className="topbar">
        <div><span className="eyebrow">THE CREATION OS</span><h1>Living Cognitive Operating System</h1></div>
        <div className="top-status">
          <span className={`status ${connection.toLowerCase()}`}>{connection}</span>
          <span>Chronicle #{state?.position ?? "—"}</span>
          <span>{state?.generated_at ? new Date(state.generated_at).toLocaleTimeString() : "—"}</span>
        </div>
      </header>

      {connection === "AUTH_REQUIRED" && <section className="auth-banner">Authentication required. Store a valid access token as <code>creation_access_token</code> in this browser session.</section>}
      {error && connection === "ERROR" && <section className="error-banner">Live state unavailable: {error}</section>}

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
            {['CREATOR','DEUS','SOPHIA','ROCKMAM','INCEPTION','CENTRAL CORE','TREE CORE'].map((name) => <li key={name}>{name}</li>)}
          </ol>
          <div className="panel-title secondary">MISSIONS</div>
          <div className="stack">
            {state?.missions.slice(-8).reverse().map((mission) => <div className="row" key={mission.id}><span>{mission.title}</span><b className={statusTone(mission.status)}>{mission.status}</b></div>)}
          </div>
        </aside>

        <section className="panel core">
          <div className="panel-title">LIVING CORE VISUALIZATION</div>
          <div className="core-map">
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
          <div className="memory-grid">{state && Object.entries(state.memory).filter(([k]) => k !== "total").map(([k,v]) => <div key={k}><span>{k}</span><strong>{v}</strong></div>)}</div>
        </aside>
      </section>

      <section className="lower-grid lower-grid-primary">
        <article className="panel"><div className="panel-title">CHRONICLE</div><div className="event-list">{chronicle.length ? chronicle.map((event) => <div className="event" key={event.event_id}><time>{new Date(event.created_at).toLocaleTimeString()}</time><span>{event.event_type}</span><small>{event.aggregate_type}</small></div>) : <div className="empty">Chronicle has no persisted events.</div>}</div></article>
        <article className="panel"><div className="panel-title">PULSE</div><div className="stack">{pulseEntries.length ? pulseEntries.map(([name, metric]) => <div className="row" key={name}><span>{name}</span><b className="good">{String(metric.value)}</b></div>) : <div className="empty">No persisted Pulse metrics.</div>}</div></article>
        <article className="panel"><div className="panel-title">TASK DAG</div><div className="dag">{missionTasks.length ? missionTasks.map((task, i) => <div className="dag-item" key={task.id}><span>{i + 1}</span><div><strong>{task.status}</strong><small>{task.attempt_count}/{task.max_attempts} attempts</small></div></div>) : <div className="empty">No task graph for selected mission.</div>}</div></article>
        <article className="panel"><div className="panel-title">SYSTEM EVENTS</div><div className="event-list">{events.length ? events.map((event) => <div className="event" key={event.event_id}><time>#{event.position}</time><span>{event.event_type}</span><small>{event.aggregate_type}</small></div>) : <div className="empty">No new events since connection.</div>}</div></article>
      </section>

      <section className="lower-grid lower-grid-secondary">
        <article className="panel projections-panel"><div className="panel-title">PROJECTIONS</div><div className="stack">{projections?.projections.map((p) => <div className="row" key={p.name}><span>{p.name}</span><b className={statusTone(p.status)}>{p.status}{p.lag ? ` · lag ${p.lag}` : ""}</b></div>)}</div></article>
      </section>
    </main>
  );
}

export default App;
