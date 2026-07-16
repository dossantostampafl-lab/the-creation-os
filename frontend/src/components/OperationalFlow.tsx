import { flowAgents, operationalSteps } from "../data/universeLayout";
import { AgentNode } from "./AgentNode";

type OperationalFlowProps = {
  runningMissions: number;
  activeAgents: number;
};

export function OperationalFlow({ runningMissions, activeAgents }: OperationalFlowProps) {
  const missionActive = runningMissions > 0;

  return (
    <section className="operational-flow" data-mission-active={missionActive} data-active-agents={activeAgents}>
      <div className="core-stack">
        {operationalSteps.map(([title, subtitle]) => (
          <article key={title} className="core-step" data-flow-active={missionActive}>
            <i />
            <div>
              <strong>{title}</strong>
              <span>{subtitle}</span>
            </div>
          </article>
        ))}
      </div>
      <div className="agent-row">
        {flowAgents.map(([title, subtitle], index) => (
          <AgentNode key={title} title={title} subtitle={subtitle} active={missionActive && index < Math.max(1, activeAgents)} />
        ))}
      </div>
      <div className="return-stack">
        <article>
          <strong>TREE CORE</strong>
          <span>Consolida resultados</span>
        </article>
        <article>
          <strong>CENTRAL CORE</strong>
          <span>Valida e integra</span>
        </article>
      </div>
    </section>
  );
}
