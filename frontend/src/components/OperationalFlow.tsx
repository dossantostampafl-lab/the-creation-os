import { flowAgents, operationalSteps } from "../data/universeLayout";
import { AgentNode } from "./AgentNode";

export function OperationalFlow() {
  return (
    <section className="operational-flow">
      <div className="core-stack">
        {operationalSteps.map(([title, subtitle]) => (
          <article key={title} className="core-step">
            <i />
            <div>
              <strong>{title}</strong>
              <span>{subtitle}</span>
            </div>
          </article>
        ))}
      </div>
      <div className="agent-row">
        {flowAgents.map(([title, subtitle]) => (
          <AgentNode key={title} title={title} subtitle={subtitle} />
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
