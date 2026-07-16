import type { Agent, ChronicleEntry, Inception, Mission, MissionManifestation, Pulse, Universe } from "../types";
import { agentsForUniverse, mergeUniverseData } from "../data/universeLayout";
import { ConnectionLayer } from "./ConnectionLayer";
import { GodCore } from "./GodCore";
import { MalkuthNode } from "./MalkuthNode";
import { OperationalFlow } from "./OperationalFlow";
import { RockmamNode } from "./RockmamNode";
import { SophiaNode } from "./SophiaNode";
import { StarfieldCanvas } from "./StarfieldCanvas";
import { UniverseGalaxy } from "./UniverseGalaxy";

type LivingUniverseProps = {
  agents: Agent[];
  universes: Universe[];
  missions: Mission[];
  inceptions: Inception[];
  chronicles: ChronicleEntry[];
  manifestations: MissionManifestation[];
  pulse: Pulse | null;
};

function isRunningMission(mission: Mission) {
  return ["running", "in_progress", "executing", "active"].includes(mission.status.toLowerCase());
}

function pulseHealth(pulse: Pulse | null) {
  if (!pulse) return "unknown";
  if (pulse.error_count > 0 || pulse.failed_tasks > 0) return "degraded";
  if (pulse.status.toLowerCase().includes("healthy") || pulse.chronicles_chain.valid) return "healthy";
  return pulse.status.toLowerCase();
}

export function LivingUniverse({ agents, universes, missions, inceptions, chronicles, manifestations, pulse }: LivingUniverseProps) {
  const visualUniverses = mergeUniverseData(universes);
  const runningMissions = pulse?.running_missions ?? missions.filter(isRunningMission).length;
  const pendingInceptions = pulse?.pending_inceptions ?? inceptions.length;
  const manifested = manifestations.filter((item) => item.manifestation_state === "MANIFESTED").length;
  const activeAgents = pulse?.active_agents ?? agents.length;
  const activity = Math.min(1, (runningMissions * 2 + pendingInceptions + manifested + activeAgents / 4) / 10);
  const health = pulseHealth(pulse);
  const flowActive = runningMissions > 0 || pendingInceptions > 0;
  const zoom = 1 + activity * 0.025;
  const panX = (activeAgents % 5 - 2) * activity * 2.2;
  const panY = (chronicles.length % 5 - 2) * activity * 1.6;

  return (
    <section
      className="living-universe"
      data-pulse-health={health}
      data-flow-active={flowActive}
      data-mission-active={runningMissions > 0}
      data-inception-active={pendingInceptions > 0}
      style={{
        "--universe-activity": activity,
        "--universe-zoom": zoom,
        "--universe-pan-x": `${panX}px`,
        "--universe-pan-y": `${panY}px`,
      } as React.CSSProperties}
    >
      <StarfieldCanvas
        activity={activity}
        health={health}
        activeAgents={activeAgents}
        runningMissions={runningMissions}
        pendingInceptions={pendingInceptions}
      />
      <div className="nebula nebula-blue" />
      <div className="nebula nebula-gold" />
      <div className="universe-viewport">
        <ConnectionLayer
          flowActive={flowActive}
          runningMissions={runningMissions}
          pendingInceptions={pendingInceptions}
          manifested={manifested}
        />
        {visualUniverses.length === 0 ? <p className="universe-empty-state">API sem Universos ativos</p> : null}
        {visualUniverses.map((universe) => {
          const realAgents = agentsForUniverse(universe, agents);
          return <UniverseGalaxy key={universe.id} universe={universe} agents={realAgents} missionActive={runningMissions > 0} />;
        })}
        <SophiaNode active={flowActive} />
        <RockmamNode active={flowActive} />
        <GodCore activity={activity} />
        <OperationalFlow runningMissions={runningMissions} activeAgents={activeAgents} />
        <MalkuthNode manifestations={manifestations} />
      </div>
    </section>
  );
}
