import type { Agent, Universe } from "../types";
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
};

export function LivingUniverse({ agents, universes }: LivingUniverseProps) {
  const visualUniverses = mergeUniverseData(universes);

  return (
    <section className="living-universe">
      <StarfieldCanvas />
      <div className="nebula nebula-blue" />
      <div className="nebula nebula-gold" />
      <ConnectionLayer />
      {visualUniverses.map((universe) => {
        const realAgents = agentsForUniverse(universe, agents);
        return <UniverseGalaxy key={universe.id} universe={universe} agents={realAgents} demo={realAgents.length === 0} />;
      })}
      <SophiaNode />
      <RockmamNode />
      <GodCore />
      <OperationalFlow />
      <MalkuthNode />
    </section>
  );
}
