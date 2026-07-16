import type { Agent, MissionManifestation, Universe } from "../types";
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
  manifestations: MissionManifestation[];
};

export function LivingUniverse({ agents, universes, manifestations }: LivingUniverseProps) {
  const visualUniverses = mergeUniverseData(universes);

  return (
    <section className="living-universe">
      <StarfieldCanvas />
      <div className="nebula nebula-blue" />
      <div className="nebula nebula-gold" />
      <ConnectionLayer />
      {visualUniverses.length === 0 ? <p className="universe-empty-state">API sem Universos ativos</p> : null}
      {visualUniverses.map((universe) => {
        const realAgents = agentsForUniverse(universe, agents);
        return <UniverseGalaxy key={universe.id} universe={universe} agents={realAgents} />;
      })}
      <SophiaNode />
      <RockmamNode />
      <GodCore />
      <OperationalFlow />
      <MalkuthNode manifestations={manifestations} />
    </section>
  );
}
