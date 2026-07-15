import { Bot, Sparkles } from "lucide-react";
import type { Agent, Universe } from "../types";

type CosmicSystemProps = {
  agents: Agent[];
  universes: Universe[];
  loadState: string;
};

function point(index: number, total: number, radius: number) {
  const safeTotal = Math.max(total, 1);
  const angle = (index / safeTotal) * Math.PI * 2 - Math.PI / 2;
  return {
    x: 50 + Math.cos(angle) * radius,
    y: 50 + Math.sin(angle) * radius * 0.72,
  };
}

function agentPoint(index: number, total: number) {
  const angle = (index / Math.max(total, 1)) * Math.PI * 2;
  const radius = 8 + (index % 4) * 4;
  return {
    x: 50 + Math.cos(angle) * radius,
    y: 50 + Math.sin(angle) * radius,
  };
}

function universesFromAgents(agents: Agent[]): Universe[] {
  const names = Array.from(new Set(agents.map((agent) => agent.universe).filter(Boolean)));
  return names.map((name) => ({ id: `derived-${name}`, code: name, name, active: true, created_at: "" }));
}

export function CosmicSystem({ agents, universes, loadState }: CosmicSystemProps) {
  const visibleUniverses = universes.length > 0 ? universes : universesFromAgents(agents);

  return (
    <section className="cosmic-system" aria-label="THE CREATION OS living universe">
      <div className="starfield stars-a" />
      <div className="starfield stars-b" />
      <div className="galactic-dust" />
      <svg className="living-lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        <path d="M50 50 C35 20, 20 55, 12 38" />
        <path d="M50 50 C70 19, 84 54, 88 34" />
        <path d="M50 50 C27 78, 63 90, 79 72" />
      </svg>

      <div className="god-core">
        <span className="god-aura" />
        <Bot size={34} />
        <strong>GOD</strong>
      </div>

      <div className="trinity-orbit orbit-one">
        <div className="orbit-node sophia">
          <Sparkles size={18} />
          <span>SOPHIA</span>
        </div>
      </div>
      <div className="trinity-orbit orbit-two">
        <div className="orbit-node rockmam">
          <Sparkles size={18} />
          <span>ROCKMAM</span>
        </div>
      </div>

      {loadState === "loading" && <p className="cosmic-state">Loading real universes and agents...</p>}
      {loadState !== "loading" && visibleUniverses.length === 0 && (
        <p className="cosmic-state">No Universes or Agents returned by the backend.</p>
      )}

      {visibleUniverses.map((universe, index) => {
        const position = point(index, visibleUniverses.length, 34);
        const universeAgents = agents.filter((agent) => agent.universe === universe.code || agent.universe === universe.name);
        return (
          <article
            key={universe.id}
            className="universe-galaxy"
            style={{ left: `${position.x}%`, top: `${position.y}%` }}
          >
            <div className="galaxy-body">
              {universeAgents.map((agent, agentIndex) => {
                const star = agentPoint(agentIndex, universeAgents.length);
                return (
                  <span
                    key={agent.id}
                    className={`agent-light ${agent.status}`}
                    style={{ left: `${star.x}%`, top: `${star.y}%` }}
                    title={`${agent.name} / ${agent.status}`}
                  />
                );
              })}
            </div>
            <strong>{universe.name}</strong>
            <span>{universeAgents.length} agents</span>
          </article>
        );
      })}
    </section>
  );
}
