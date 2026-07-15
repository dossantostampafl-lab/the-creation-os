import type { Agent } from "../types";
import type { UniverseVisual } from "../data/universeLayout";

type UniverseGalaxyProps = {
  universe: UniverseVisual;
  agents: Agent[];
  demo: boolean;
};

function displayAgents(universe: UniverseVisual, agents: Agent[]) {
  if (agents.length > 0) return agents.length;
  return universe.agents;
}

export function UniverseGalaxy({ universe, agents, demo }: UniverseGalaxyProps) {
  const count = displayAgents(universe, agents);
  const points = Array.from({ length: count }, (_, index) => index);

  return (
    <article
      className={`universe-galaxy exact-galaxy ${universe.id}`}
      style={{
        left: `${universe.left}%`,
        top: `${universe.top}%`,
        "--galaxy-color": universe.color,
        "--galaxy-soft": universe.colorSoft,
      } as React.CSSProperties}
      data-source={demo ? "DEMO_VISUAL_DATA" : "API"}
    >
      <div className="galaxy-icon">{iconFor(universe.icon)}</div>
      <div className="spiral-disk">
        <span className="spiral-core" />
        {points.map((point) => (
          <i key={point} style={{ "--star-index": point } as React.CSSProperties} />
        ))}
      </div>
      <div className="galaxy-label">
        <strong>{universe.title}</strong>
        <span>{count} {count === 1 ? "AGENTE" : "AGENTES"}</span>
        <p>{universe.description}</p>
      </div>
    </article>
  );
}

function iconFor(icon: string) {
  switch (icon) {
    case "book":
      return "□";
    case "leaf":
      return "◒";
    case "code":
      return "</>";
    case "shield":
      return "⬟";
    case "users":
      return "●●";
    case "box":
      return "◇";
    default:
      return "✦";
  }
}
